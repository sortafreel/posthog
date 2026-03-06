"""Utility to query the `events` table with the same column schema as `ai_events`.

When `ai_events` has no data (expired via TTL or predates dual-write), query
runners fall back to the `events` table.  This module provides a HogQL
subquery that projects `events` rows into the `ai_events` column layout so
the outer aggregation query works unchanged — just swap the FROM clause.

Heavy columns (input, output, …) are available for pre-split data (full
properties in `events`) but empty for post-split data whose TTL has expired.
This is by design — heavy content is intentionally lost after 30 days.
"""

# Subquery string that can be dropped into a HogQL FROM clause.
# Aliased as ``ai_events`` so every outer-query column reference resolves
# without changes.
EVENTS_AS_AI_EVENTS = """(
    SELECT
        uuid,
        event,
        timestamp,
        team_id,
        distinct_id,
        person_id,
        properties,

        JSONExtractString(properties, '$ai_trace_id') AS trace_id,
        JSONExtractString(properties, '$ai_session_id') AS session_id,
        JSONExtractString(properties, '$ai_parent_id') AS parent_id,
        JSONExtractString(properties, '$ai_span_id') AS span_id,
        JSONExtractString(properties, '$ai_generation_id') AS generation_id,

        JSONExtractString(properties, '$ai_span_name') AS span_name,
        JSONExtractString(properties, '$ai_trace_name') AS trace_name,

        JSONExtractInt(properties, '$ai_input_tokens') AS input_tokens,
        JSONExtractInt(properties, '$ai_output_tokens') AS output_tokens,

        JSONExtractFloat(properties, '$ai_input_cost_usd') AS input_cost_usd,
        JSONExtractFloat(properties, '$ai_output_cost_usd') AS output_cost_usd,
        JSONExtractFloat(properties, '$ai_total_cost_usd') AS total_cost_usd,

        JSONExtractFloat(properties, '$ai_latency') AS latency,

        if(JSONExtractString(properties, '$ai_is_error') = 'true', 1, 0) AS is_error,
        JSONExtractString(properties, '$ai_error_normalized') AS error_normalized,

        JSONExtractRaw(properties, '$ai_input') AS input,
        JSONExtractRaw(properties, '$ai_output') AS output,
        JSONExtractRaw(properties, '$ai_output_choices') AS output_choices,
        JSONExtractRaw(properties, '$ai_input_state') AS input_state,
        JSONExtractRaw(properties, '$ai_output_state') AS output_state,
        JSONExtractRaw(properties, '$ai_tools') AS tools
    FROM events
    WHERE event IN (
        '$ai_generation', '$ai_span', '$ai_trace', '$ai_embedding',
        '$ai_metric', '$ai_feedback', '$ai_evaluation'
    )
) AS ai_events"""
