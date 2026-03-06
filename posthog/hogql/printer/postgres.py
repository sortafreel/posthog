from collections.abc import Callable
from typing import Literal

from posthog.hogql import ast
from posthog.hogql.ast import AST
from posthog.hogql.constants import HogQLGlobalSettings
from posthog.hogql.context import HogQLContext
from posthog.hogql.errors import ImpossibleASTError, QueryError
from posthog.hogql.escape_sql import escape_postgres_identifier
from posthog.hogql.printer.base import HogQLPrinter

# Simple 1:1 function name renames (ClickHouse name → Postgres name)
_POSTGRES_FUNCTION_RENAMES: dict[str, str] = {
    "ifNull": "COALESCE",
    "groupArray": "ARRAY_AGG",
    "arrayJoin": "UNNEST",
    "JSONExtractString": "json_extract_path_text",
    "JSONExtractRaw": "json_extract_path",
    "JSONExtractArrayRaw": "json_extract_path",
    "fromUnixTimestamp": "TO_TIMESTAMP",
    "replaceAll": "REPLACE",
    "replaceRegexpAll": "REGEXP_REPLACE",
    "arrayStringConcat": "ARRAY_TO_STRING",
    "JSONLength": "json_array_length",
    "toTypeName": "pg_typeof",
    "formatDateTime": "TO_CHAR",
    "now": "NOW",
}


def _make_cast_handler(pg_type: str) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        return f"CAST({args[0]} AS {pg_type})"

    return handler


def _make_extract_handler(unit: str) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        return f"EXTRACT({unit} FROM {args[0]})"

    return handler


def _make_date_trunc_handler(unit: str, cast_to_date: bool = False) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        expr = f"DATE_TRUNC('{unit}', {args[0]})"
        if cast_to_date:
            return f"CAST({expr} AS DATE)"
        return expr

    return handler


def _make_interval_handler(unit: str) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        return f"({args[0]} * INTERVAL '{unit}')"

    return handler


def _make_date_add_handler(unit: str, op: str = "+") -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        return f"({args[0]} {op} {args[1]} * INTERVAL '{unit}')"

    return handler


def _handle_to_unix_timestamp(args: list[str]) -> str:
    return f"CAST(EXTRACT(EPOCH FROM {args[0]}) AS BIGINT)"


def _handle_to_yyyymm(args: list[str]) -> str:
    return f"CAST(TO_CHAR({args[0]}, 'YYYYMM') AS INTEGER)"


def _handle_to_last_day_of_month(args: list[str]) -> str:
    return f"CAST((DATE_TRUNC('month', {args[0]}) + INTERVAL '1 month' - INTERVAL '1 day') AS DATE)"


def _handle_today(args: list[str]) -> str:
    return "CURRENT_DATE"


def _handle_yesterday(args: list[str]) -> str:
    return "(CURRENT_DATE - INTERVAL '1 day')"


def _handle_if(args: list[str]) -> str:
    return f"CASE WHEN {args[0]} THEN {args[1]} ELSE {args[2]} END"


def _handle_multi_if(args: list[str]) -> str:
    # multiIf(c1, v1, c2, v2, ..., default)
    # Pairs of (condition, value) followed by a default
    parts = ["CASE"]
    i = 0
    while i < len(args) - 1:
        parts.append(f"WHEN {args[i]} THEN {args[i + 1]}")
        i += 2
    parts.append(f"ELSE {args[-1]} END")
    return " ".join(parts)


def _handle_empty(args: list[str]) -> str:
    return f"({args[0]} IS NULL OR {args[0]} = '')"


def _handle_not_empty(args: list[str]) -> str:
    return f"({args[0]} IS NOT NULL AND {args[0]} != '')"


def _handle_is_null(args: list[str]) -> str:
    return f"({args[0]} IS NULL)"


def _handle_is_not_null(args: list[str]) -> str:
    return f"({args[0]} IS NOT NULL)"


def _handle_noop(args: list[str]) -> str:
    return args[0]


def _make_json_cast_handler(pg_type: str) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        # JSONExtractInt(json, key1, key2, ...) → CAST(json_extract_path_text(json, key1, key2, ...) AS type)
        inner_args = ", ".join(args)
        return f"CAST(json_extract_path_text({inner_args}) AS {pg_type})"

    return handler


def _handle_match(args: list[str]) -> str:
    return f"({args[0]} ~ {args[1]})"


def _handle_split_by(args: list[str]) -> str:
    # splitByString(sep, str) → STRING_TO_ARRAY(str, sep) — args are reversed
    return f"STRING_TO_ARRAY({args[1]}, {args[0]})"


def _handle_uniq(args: list[str]) -> str:
    return f"COUNT(DISTINCT {args[0]})"


def _handle_to_yyyymmdd(args: list[str]) -> str:
    return f"CAST(TO_CHAR({args[0]}, 'YYYYMMDD') AS INTEGER)"


def _handle_to_yyyymmddhhmmss(args: list[str]) -> str:
    return f"CAST(TO_CHAR({args[0]}, 'YYYYMMDDHH24MISS') AS BIGINT)"


def _make_sub_hour_trunc_handler(minutes: int) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        return (
            f"DATE_TRUNC('minute', {args[0]}) - "
            f"CAST(EXTRACT(MINUTE FROM {args[0]}) AS INTEGER) % {minutes} * INTERVAL '1 minute'"
        )

    return handler


def _handle_to_last_day_of_week(args: list[str]) -> str:
    return f"CAST((DATE_TRUNC('week', {args[0]}) + INTERVAL '6 day') AS DATE)"


def _handle_replace_one(args: list[str]) -> str:
    # Postgres REGEXP_REPLACE defaults to first occurrence only
    return f"REGEXP_REPLACE({args[0]}, {args[1]}, {args[2]})"


def _handle_count_if(args: list[str]) -> str:
    if len(args) == 1:
        return f"count(*) FILTER (WHERE {args[0]})"
    return f"count({args[0]}) FILTER (WHERE {args[1]})"


def _make_if_combinator_handler(pg_base_fn: str) -> Callable[[list[str]], str]:
    def handler(args: list[str]) -> str:
        agg_args = args[:-1]
        condition = args[-1]
        return f"{pg_base_fn}({', '.join(agg_args)}) FILTER (WHERE {condition})"

    return handler


def _handle_uniq_if(args: list[str]) -> str:
    agg_args = args[:-1]
    condition = args[-1]
    return f"COUNT(DISTINCT {', '.join(agg_args)}) FILTER (WHERE {condition})"


def _handle_date_diff(args: list[str]) -> str:
    # DATE_PART extracts from an INTERVAL, so both operands must be TIMESTAMP
    # (TIMESTAMP - TIMESTAMP → INTERVAL, whereas DATE - DATE → INTEGER which DATE_PART rejects)
    return f"DATE_PART({args[0]}, CAST({args[2]} AS TIMESTAMP) - CAST({args[1]} AS TIMESTAMP))"


# Complex handlers: ClickHouse function name → callable(list[rendered_arg_strings]) → SQL string
_POSTGRES_FUNCTION_HANDLERS: dict[str, Callable[[list[str]], str]] = {
    # Type conversions
    "toDate": _make_cast_handler("DATE"),
    "toDateTime": _make_cast_handler("TIMESTAMP"),
    "toString": _make_cast_handler("TEXT"),
    "toInt": _make_cast_handler("BIGINT"),
    "toFloat": _make_cast_handler("DOUBLE PRECISION"),
    "toFloatOrZero": _make_cast_handler("DOUBLE PRECISION"),
    "toIntOrZero": _make_cast_handler("BIGINT"),
    "toBool": _make_cast_handler("BOOLEAN"),
    "toUUID": _make_cast_handler("UUID"),
    # Date extraction
    "toYear": _make_extract_handler("YEAR"),
    "toQuarter": _make_extract_handler("QUARTER"),
    "toMonth": _make_extract_handler("MONTH"),
    "toDayOfMonth": _make_extract_handler("DAY"),
    "toDayOfWeek": _make_extract_handler("DOW"),
    "toDayOfYear": _make_extract_handler("DOY"),
    "toHour": _make_extract_handler("HOUR"),
    "toMinute": _make_extract_handler("MINUTE"),
    "toSecond": _make_extract_handler("SECOND"),
    "toUnixTimestamp": _handle_to_unix_timestamp,
    "toYYYYMM": _handle_to_yyyymm,
    # Date truncation
    "toStartOfYear": _make_date_trunc_handler("year", cast_to_date=True),
    "toStartOfQuarter": _make_date_trunc_handler("quarter", cast_to_date=True),
    "toStartOfMonth": _make_date_trunc_handler("month", cast_to_date=True),
    "toStartOfWeek": _make_date_trunc_handler("week", cast_to_date=True),
    "toMonday": _make_date_trunc_handler("week", cast_to_date=True),
    "toStartOfDay": _make_date_trunc_handler("day"),
    "toStartOfHour": _make_date_trunc_handler("hour"),
    "toStartOfMinute": _make_date_trunc_handler("minute"),
    "toStartOfSecond": _make_date_trunc_handler("second"),
    "toLastDayOfMonth": _handle_to_last_day_of_month,
    # Date generators
    "today": _handle_today,
    "yesterday": _handle_yesterday,
    # Intervals
    "toIntervalSecond": _make_interval_handler("1 second"),
    "toIntervalMinute": _make_interval_handler("1 minute"),
    "toIntervalHour": _make_interval_handler("1 hour"),
    "toIntervalDay": _make_interval_handler("1 day"),
    "toIntervalWeek": _make_interval_handler("1 week"),
    "toIntervalMonth": _make_interval_handler("1 month"),
    "toIntervalQuarter": _make_interval_handler("3 month"),
    "toIntervalYear": _make_interval_handler("1 year"),
    # Date arithmetic
    "addSeconds": _make_date_add_handler("1 second"),
    "addMinutes": _make_date_add_handler("1 minute"),
    "addHours": _make_date_add_handler("1 hour"),
    "addDays": _make_date_add_handler("1 day"),
    "addWeeks": _make_date_add_handler("1 week"),
    "addMonths": _make_date_add_handler("1 month"),
    "addQuarters": _make_date_add_handler("3 month"),
    "addYears": _make_date_add_handler("1 year"),
    "subtractSeconds": _make_date_add_handler("1 second", op="-"),
    "subtractMinutes": _make_date_add_handler("1 minute", op="-"),
    "subtractHours": _make_date_add_handler("1 hour", op="-"),
    "subtractDays": _make_date_add_handler("1 day", op="-"),
    "subtractWeeks": _make_date_add_handler("1 week", op="-"),
    "subtractMonths": _make_date_add_handler("1 month", op="-"),
    "subtractQuarters": _make_date_add_handler("3 month", op="-"),
    "subtractYears": _make_date_add_handler("1 year", op="-"),
    # Date diff
    "dateDiff": _handle_date_diff,
    # Conditional
    "if": _handle_if,
    "multiIf": _handle_multi_if,
    # Null/empty
    "empty": _handle_empty,
    "notEmpty": _handle_not_empty,
    "isNull": _handle_is_null,
    "isNotNull": _handle_is_not_null,
    "assumeNotNull": _handle_noop,
    "toNullable": _handle_noop,
    # JSON with type cast
    "JSONExtractInt": _make_json_cast_handler("INTEGER"),
    "JSONExtractFloat": _make_json_cast_handler("DOUBLE PRECISION"),
    "JSONExtractBool": _make_json_cast_handler("BOOLEAN"),
    # String
    "match": _handle_match,
    "splitByString": _handle_split_by,
    "splitByChar": _handle_split_by,
    # Aggregation
    "uniq": _handle_uniq,
    "uniqExact": _handle_uniq,
    # More date extraction
    "toYYYYMMDD": _handle_to_yyyymmdd,
    "toYYYYMMDDhhmmss": _handle_to_yyyymmddhhmmss,
    "toISOWeek": _make_extract_handler("WEEK"),
    "toISOYear": _make_extract_handler("ISOYEAR"),
    # Sub-hour truncation
    "toStartOfFiveMinutes": _make_sub_hour_trunc_handler(5),
    "toStartOfTenMinutes": _make_sub_hour_trunc_handler(10),
    "toStartOfFifteenMinutes": _make_sub_hour_trunc_handler(15),
    # ISO year start (same as toStartOfYear)
    "toStartOfISOYear": _make_date_trunc_handler("year", cast_to_date=True),
    "toLastDayOfWeek": _handle_to_last_day_of_week,
    # More type conversions
    "toDecimal": _make_cast_handler("DECIMAL"),
    "toDateTime64": _make_cast_handler("TIMESTAMP"),
    "toFloatOrDefault": _make_cast_handler("DOUBLE PRECISION"),
    # More JSON
    "JSONExtractUInt": _make_json_cast_handler("INTEGER"),
    # String
    "replaceOne": _handle_replace_one,
    "replaceRegexpOne": _handle_replace_one,
    # Aggregate *If combinators
    "countIf": _handle_count_if,
    "sumIf": _make_if_combinator_handler("sum"),
    "avgIf": _make_if_combinator_handler("avg"),
    "minIf": _make_if_combinator_handler("min"),
    "maxIf": _make_if_combinator_handler("max"),
    "anyIf": _make_if_combinator_handler("any"),
    "uniqIf": _handle_uniq_if,
    "uniqExactIf": _handle_uniq_if,
    "groupArrayIf": _make_if_combinator_handler("ARRAY_AGG"),
}


# Standard SQL functions that work unchanged in both Postgres and DuckDB.
# Any ClickHouse function NOT in handlers, renames, or this set raises a compile-time error.
_POSTGRES_PASSTHROUGH_FUNCTIONS: frozenset[str] = frozenset(
    {
        # Aggregates
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "any",
        "countDistinct",
        # Math
        "abs",
        "floor",
        "ceil",
        "round",
        "sqrt",
        "pow",
        "power",
        "exp",
        "log",
        "log2",
        "log10",
        "ln",
        "sign",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "pi",
        "e",
        "degrees",
        "radians",
        "cbrt",
        "greatest",
        "least",
        # String
        "lower",
        "upper",
        "trim",
        "ltrim",
        "rtrim",
        "substring",
        "concat",
        "length",
        "left",
        "right",
        "position",
        "reverse",
        "replace",
        "lpad",
        "rpad",
        "repeat",
        "initcap",
        "ascii",
        "startsWith",
        "endsWith",
        # Window
        "row_number",
        "rank",
        "dense_rank",
        "lag",
        "lead",
        "first_value",
        "last_value",
        "nth_value",
        # Null
        "coalesce",
        "nullif",
        # Other
        "md5",
        "rand",
        "generateSeries",
        "range",
    }
)


class PostgresPrinter(HogQLPrinter):
    def __init__(
        self,
        context: HogQLContext,
        dialect: Literal["postgres"],
        stack: list[AST] | None = None,
        settings: HogQLGlobalSettings | None = None,
        pretty: bool = False,
    ):
        super().__init__(context=context, dialect=dialect, stack=stack, settings=settings, pretty=pretty)

    def visit_field(self, node: ast.Field):
        if node.type is None:
            field = ".".join([self._print_hogql_identifier_or_index(identifier) for identifier in node.chain])
            raise ImpossibleASTError(f"Field {field} has no type")

        if isinstance(node.type, ast.LazyJoinType) or isinstance(node.type, ast.VirtualTableType):
            raise QueryError(f"Can't select a table when a column is expected: {'.'.join(map(str, node.chain))}")

        return self.visit(node.type)

    def visit_call(self, node: ast.Call):
        args = [self.visit(arg) for arg in node.args]

        # Complex handlers: structural transforms (CAST, CASE, EXTRACT, etc.)
        handler = _POSTGRES_FUNCTION_HANDLERS.get(node.name)
        if handler is not None:
            return handler(args)

        # Simple renames: just swap the function name
        pg_name = _POSTGRES_FUNCTION_RENAMES.get(node.name, node.name)

        # If the name wasn't renamed and isn't a known passthrough, it's unsupported
        if pg_name == node.name and node.name not in _POSTGRES_PASSTHROUGH_FUNCTIONS:
            raise QueryError(
                f"Function '{node.name}' is not supported in the Postgres dialect. "
                f"It may only be available in ClickHouse."
            )

        return f"{pg_name}({', '.join(args)})"

    def visit_and(self, node):
        return f"({' AND '.join([f'({self.visit(expr)})' for expr in node.exprs])})"

    def visit_or(self, node):
        return f"({' OR '.join([f'({self.visit(expr)})' for expr in node.exprs])})"

    def visit_not(self, node):
        return f"(NOT {self.visit(node.expr)})"

    def visit_table_type(self, type: ast.TableType):
        return type.table.to_printed_clickhouse(self.context)

    def _visit_in_values(self, node: ast.Expr) -> str:
        if isinstance(node, ast.Tuple):
            return f"({', '.join(self.visit(value) for value in node.exprs)})"
        elif isinstance(node, ast.Constant):
            return f"({self.visit(node)})"

        return self.visit(node)

    def visit_compare_operation(self, node: ast.CompareOperation):
        left = self.visit(node.left)

        if node.op in (ast.CompareOperationOp.In, ast.CompareOperationOp.NotIn):
            right = self._visit_in_values(node.right)
        else:
            right = self.visit(node.right)

        return self._get_compare_op(node.op, left, right)

    def _get_compare_op(self, op: ast.CompareOperationOp, left: str, right: str) -> str:
        if op == ast.CompareOperationOp.Eq:
            return f"({left} = {right})"
        elif op == ast.CompareOperationOp.NotEq:
            return f"({left} != {right})"
        elif op == ast.CompareOperationOp.Like:
            return f"({left} LIKE {right})"
        elif op == ast.CompareOperationOp.NotLike:
            return f"({left} NOT LIKE {right})"
        elif op == ast.CompareOperationOp.ILike:
            return f"({left} ILIKE {right})"
        elif op == ast.CompareOperationOp.NotILike:
            return f"({left} NOT ILIKE {right})"
        elif op == ast.CompareOperationOp.In:
            return f"({left} IN {right})"
        elif op == ast.CompareOperationOp.NotIn:
            return f"({left} NOT IN {right})"
        elif op == ast.CompareOperationOp.Regex:
            return f"({left} ~ {right})"
        elif op == ast.CompareOperationOp.NotRegex:
            return f"({left} !~ {right})"
        elif op == ast.CompareOperationOp.IRegex:
            return f"({left} ~* {right})"
        elif op == ast.CompareOperationOp.NotIRegex:
            return f"({left} !~* {right})"
        elif op == ast.CompareOperationOp.Gt:
            return f"({left} > {right})"
        elif op == ast.CompareOperationOp.GtEq:
            return f"({left} >= {right})"
        elif op == ast.CompareOperationOp.Lt:
            return f"({left} < {right})"
        elif op == ast.CompareOperationOp.LtEq:
            return f"({left} <= {right})"
        else:
            raise ImpossibleASTError(f"Unknown CompareOperationOp: {op.name}")

    def _print_table_ref(self, table_type: ast.TableType | ast.LazyTableType, node: ast.JoinExpr) -> str:
        return table_type.table.to_printed_clickhouse(self.context)

    def _ensure_team_id_where_clause(
        self,
        table_type: ast.TableType | ast.LazyTableType,
        node_type: ast.TableOrSelectType,
    ):
        # Team ID filtering is not required for Postgres queries
        pass

    def _print_identifier(self, name: str) -> str:
        return escape_postgres_identifier(name)

    def _json_property_args(self, chain):
        return [self._print_escaped_string(name) for name in chain]

    def _unsafe_json_extract_trim_quotes(self, unsafe_field, unsafe_args):
        if len(unsafe_args) == 0:
            return unsafe_field

        json_expr = unsafe_field
        for arg in unsafe_args[:-1]:
            json_expr = f"({json_expr}) -> {arg}"

        return f"({json_expr}) ->> {unsafe_args[-1]}"

    def _print_select_columns(self, columns):
        columns_sql = []
        for column in columns:
            # Unwrap hidden aliases
            if (isinstance(column, ast.Alias)) and column.hidden:
                column = column.expr

            if isinstance(column, ast.Field) and isinstance(column.type, ast.PropertyType):
                alias_name = ".".join(map(str, column.chain))
                column = ast.Alias(alias=alias_name, expr=column)

            columns_sql.append(self.visit(column))
        return columns_sql

    def visit_arithmetic_operation(self, node):
        if node.op == ast.ArithmeticOperationOp.Add:
            return f"({self.visit(node.left)} + {self.visit(node.right)})"
        elif node.op == ast.ArithmeticOperationOp.Sub:
            return f"({self.visit(node.left)} - {self.visit(node.right)})"
        elif node.op == ast.ArithmeticOperationOp.Mult:
            return f"({self.visit(node.left)} * {self.visit(node.right)})"
        elif node.op == ast.ArithmeticOperationOp.Div:
            return f"({self.visit(node.left)} / {self.visit(node.right)})"
        elif node.op == ast.ArithmeticOperationOp.Mod:
            return f"({self.visit(node.left)} % {self.visit(node.right)})"
        else:
            raise ImpossibleASTError(f"Unknown ArithmeticOperationOp {node.op}")

    def visit_tuple(self, node: ast.Tuple) -> str:
        values = [self.visit(expr) for expr in node.exprs]

        if len(values) == 1:
            # Parentheses around a single value are just grouping in Postgres. Use ROW() to construct a 1-column tuple.
            return f"ROW({values[0]})"

        return f"({', '.join(values)})"

    def visit_type_cast(self, node):
        expr_sql = self.visit(node.expr)
        return f"CAST({expr_sql} AS {escape_postgres_identifier(node.type_name)})"

    def visit_cte(self, node: ast.CTE):
        materialization_hint = (
            "" if node.materialized is None else ("MATERIALIZED " if node.materialized else "NOT MATERIALIZED ")
        )

        if node.cte_type == "subquery":
            columns_sql = (
                "" if node.columns is None else f"({', '.join(self._print_identifier(col) for col in node.columns)})"
            )
            using_key_sql = (
                ""
                if node.using_key is None
                else f" USING KEY ({', '.join(self._print_identifier(col) for col in node.using_key)})"
            )
            return f"{self._print_identifier(node.name)}{columns_sql}{using_key_sql} AS {materialization_hint}{self.visit(node.expr)}"

        return super().visit_cte(node)
