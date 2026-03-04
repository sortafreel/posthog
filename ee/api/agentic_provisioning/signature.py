import re
import hmac
import time
import hashlib

from django.conf import settings

from rest_framework.request import Request
from rest_framework.response import Response

SUPPORTED_VERSIONS = ["0.1d"]
API_VERSION = SUPPORTED_VERSIONS[0]
SIGNATURE_HEADER = "Stripe-Signature"
API_VERSION_HEADER = "API-Version"
MAX_TIMESTAMP_DRIFT_SECONDS = 300


def verify_stripe_signature(request: Request) -> Response | None:
    """Verify the Stripe-Signature HMAC and API-Version header.

    Returns None if verification passes, or an error Response if it fails.
    Called at the top of every view (Vercel-style, not middleware).
    """
    api_version = request.META.get("HTTP_API_VERSION", "")
    if api_version not in SUPPORTED_VERSIONS:
        return Response(
            {
                "error": {
                    "code": "invalid_api_version",
                    "message": f"Supported API-Versions: {', '.join(SUPPORTED_VERSIONS)}",
                }
            },
            status=400,
        )

    secret = settings.STRIPE_APP_SECRET_KEY
    if not secret:
        return Response({"error": {"code": "server_error", "message": "Signing secret not configured"}}, status=500)

    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    parsed = _parse_signature_header(sig_header)
    if parsed is None:
        return Response(
            {"error": {"code": "invalid_signature", "message": "Missing or malformed Stripe-Signature header"}},
            status=401,
        )

    timestamp_str, signature_hex = parsed

    now = int(time.time())
    timestamp = int(timestamp_str)
    if abs(now - timestamp) > MAX_TIMESTAMP_DRIFT_SECONDS:
        return Response(
            {"error": {"code": "invalid_signature", "message": "Timestamp too old or too far in the future"}},
            status=401,
        )

    body = request.body
    expected_hex = _compute_hmac(secret, timestamp_str, body)

    if not hmac.compare_digest(expected_hex.lower(), signature_hex.lower()):
        return Response(
            {"error": {"code": "invalid_signature", "message": "Signature verification failed"}}, status=401
        )

    return None


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Compute HMAC-SHA256 signature for a request body. Exposed for testing."""
    return _compute_hmac(secret, str(timestamp), body)


def _compute_hmac(secret: str, timestamp_str: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), digestmod=hashlib.sha256)
    mac.update(f"{timestamp_str}.".encode())
    mac.update(body)
    return mac.digest().hex()


_TIMESTAMP_RE = re.compile(r"^\d{1,12}$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _parse_signature_header(header: str) -> tuple[str, str] | None:
    """Parse 't=<timestamp>,v1=<hex>' into (timestamp_str, hex). Returns None on failure.

    Splits on ',' and matches parts by prefix so that extra fields (e.g. v2=...)
    added in future protocol versions don't break parsing.
    """
    if not header:
        return None

    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)

    timestamp_str = parts.get("t")
    signature_hex = parts.get("v1")

    if not timestamp_str or not _TIMESTAMP_RE.fullmatch(timestamp_str):
        return None
    if not signature_hex or not _HEX64_RE.fullmatch(signature_hex):
        return None

    return timestamp_str, signature_hex
