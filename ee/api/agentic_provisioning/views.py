from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import structlog
from oauthlib.common import generate_token as generate_oauth_client_id
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.exceptions_capture import capture_exception
from posthog.models.integration import StripeIntegration
from posthog.models.oauth import OAuthAccessToken, OAuthApplication, OAuthRefreshToken, find_oauth_refresh_token
from posthog.models.team.team import Team
from posthog.models.user import User
from posthog.models.utils import generate_random_oauth_access_token, generate_random_oauth_refresh_token
from posthog.utils import get_instance_region

from . import AUTH_CODE_CACHE_PREFIX, STRIPE_APP_NAME
from .authentication import StripeProvisioningBearerAuthentication
from .region_proxy import stripe_region_proxy
from .signature import SUPPORTED_VERSIONS, verify_stripe_signature

logger = structlog.get_logger(__name__)

ACCESS_TOKEN_EXPIRY_SECONDS = 365 * 24 * 3600
AUTH_CODE_TTL_SECONDS = 300
DEEP_LINK_TTL_SECONDS = 600
DEEP_LINK_CACHE_PREFIX = "stripe_app_deep_link:"


# ---------------------------------------------------------------------------
# GET /provisioning/health
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def provisioning_health(request: Request) -> Response:
    error = verify_stripe_signature(request)
    if error:
        return error

    return Response({"supported_versions": SUPPORTED_VERSIONS, "status": "ok"})


# ---------------------------------------------------------------------------
# GET /provisioning/services
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def provisioning_services(request: Request) -> Response:
    error = verify_stripe_signature(request)
    if error:
        return error

    return Response(
        {
            "data": [
                {
                    "id": "posthog_analytics",
                    "description": "Product analytics, feature flags, session replay, and more",
                    "categories": ["analytics", "feature_flags", "observability"],
                    "pricing": {"type": "free"},
                }
            ],
            "next_cursor": "",
        }
    )


# ---------------------------------------------------------------------------
# POST /provisioning/account_requests
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@stripe_region_proxy(strategy="body_region")
def account_requests(request: Request) -> Response:
    data = request.data
    request_id = data.get("id", "")
    email = data.get("email")
    if not email:
        return Response(
            {"type": "error", "error": {"code": "invalid_request", "message": "email is required"}}, status=400
        )

    scopes = data.get("scopes", [])
    confirmation_secret = data.get("confirmation_secret", "")
    expires_at_str = data.get("expires_at", "")
    configuration = data.get("configuration") or {}
    orchestrator = data.get("orchestrator") or {}

    if expires_at_str:
        expires_at = parse_datetime(expires_at_str)
        if expires_at is None:
            return Response(
                {"type": "error", "error": {"code": "invalid_request", "message": "Invalid expires_at format"}},
                status=400,
            )
        if expires_at < timezone.now():
            return Response(
                {"type": "error", "error": {"code": "expired", "message": "Account request has expired"}},
                status=400,
            )

    stripe_account_id = ""
    if orchestrator.get("type") == "stripe" and orchestrator.get("stripe"):
        stripe_account_id = orchestrator["stripe"].get("account", "")

    region = (configuration.get("region") or "US").upper()

    existing_user = User.objects.filter(email=email).first()

    if existing_user:
        logger.info("stripe_app.account_request.existing_user", email=email)
        return _handle_existing_user(request_id, existing_user, confirmation_secret, scopes)

    logger.info("stripe_app.account_request.new_user", email=email, region=region)
    return _handle_new_user(request_id, data, email, scopes, stripe_account_id, region)


def _handle_existing_user(
    request_id: str,
    user: User,
    confirmation_secret: str,
    scopes: list[str],
) -> Response:
    authorize_url = _build_authorize_url(confirmation_secret, scopes)
    return Response(
        {
            "id": request_id,
            "type": "requires_auth",
            "requires_auth": {
                "type": "redirect",
                "redirect": {"url": authorize_url},
            },
        }
    )


def _handle_new_user(
    request_id: str,
    data: dict,
    email: str,
    scopes: list[str],
    stripe_account_id: str,
    region: str,
) -> Response:
    name = data.get("name", "")
    first_name = name.split(" ")[0] if name else ""

    try:
        organization, team, user = User.objects.bootstrap(
            organization_name=f"Stripe ({email})",
            email=email,
            password=None,
            first_name=first_name,
        )
    except IntegrityError:
        existing = User.objects.filter(email=email).first()
        if existing:
            return _handle_existing_user(request_id, existing, data.get("confirmation_secret", ""), scopes)
        return Response(
            {
                "id": request_id,
                "type": "error",
                "error": {"code": "account_creation_failed", "message": "Failed to create account"},
            },
            status=500,
        )
    except Exception as e:
        logger.warning("stripe_app.account_request.bootstrap_failed", email=email, error=str(e))
        capture_exception(e)
        return Response(
            {
                "id": request_id,
                "type": "error",
                "error": {"code": "account_creation_failed", "message": "Failed to create account"},
            },
            status=500,
        )

    code = secrets.token_urlsafe(32)
    cache_key = f"{AUTH_CODE_CACHE_PREFIX}{code}"
    cache.set(
        cache_key,
        {
            "user_id": user.id,
            "org_id": str(organization.id),
            "team_id": team.id,
            "stripe_account_id": stripe_account_id,
            "scopes": scopes,
            "region": region,
        },
        timeout=AUTH_CODE_TTL_SECONDS,
    )

    return Response({"id": request_id, "type": "oauth", "oauth": {"code": code}})


def _build_authorize_url(confirmation_secret: str, scopes: list[str]) -> str:
    base = settings.SITE_URL.rstrip("/")
    oauth_app = _get_stripe_oauth_app()
    client_id = oauth_app.client_id if oauth_app else ""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "state": confirmation_secret,
        "scope": " ".join(scopes),
    }
    return f"{base}/oauth/authorize?{urlencode(params)}"


# ---------------------------------------------------------------------------
# POST /oauth/token
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@stripe_region_proxy(strategy="token_lookup")
def oauth_token(request: Request) -> Response:
    grant_type = request.data.get("grant_type", "")

    if grant_type == "authorization_code":
        return _exchange_authorization_code(request)
    elif grant_type == "refresh_token":
        return _exchange_refresh_token(request)
    else:
        return Response(
            {"error": "unsupported_grant_type", "error_description": f"Unsupported grant_type: {grant_type}"},
            status=400,
        )


def _exchange_authorization_code(request: Request) -> Response:
    code = request.data.get("code", "")
    if not code:
        return Response({"error": "invalid_request", "error_description": "code is required"}, status=400)

    cache_key = f"{AUTH_CODE_CACHE_PREFIX}{code}"
    code_data = cache.get(cache_key)
    if code_data is None:
        return Response(
            {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"}, status=400
        )

    # Delete atomically — if another request already consumed it, treat as invalid
    if not cache.delete(cache_key):
        return Response(
            {"error": "invalid_grant", "error_description": "Invalid or expired authorization code"}, status=400
        )

    user_id = code_data["user_id"]
    team_id = code_data["team_id"]
    scopes = code_data.get("scopes", [])

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("stripe_app.token_exchange.user_not_found", user_id=user_id)
        capture_exception(Exception("Stripe APP token exchange: user not found"))
        return Response({"error": "invalid_grant", "error_description": "User not found"}, status=400)

    oauth_app = _get_stripe_oauth_app()
    scope_str = " ".join(scopes) if scopes else StripeIntegration.SCOPES

    access_token_value = generate_random_oauth_access_token(None)
    access_token = OAuthAccessToken.objects.create(
        application=oauth_app,
        token=access_token_value,
        user=user,
        expires=timezone.now() + timedelta(seconds=ACCESS_TOKEN_EXPIRY_SECONDS),
        scope=scope_str,
        scoped_teams=[team_id],
    )

    refresh_token_value = generate_random_oauth_refresh_token(None)
    OAuthRefreshToken.objects.create(
        application=oauth_app,
        token=refresh_token_value,
        user=user,
        access_token=access_token,
        scoped_teams=[team_id],
    )

    account_id = str(code_data.get("org_id", ""))
    logger.info("stripe_app.token_exchange.success", user_id=user_id, team_id=team_id)

    return Response(
        {
            "token_type": "bearer",
            "access_token": access_token_value,
            "refresh_token": refresh_token_value,
            "expires_in": ACCESS_TOKEN_EXPIRY_SECONDS,
            "account": {
                "id": account_id,
                "payment_credentials": "provider",
            },
        }
    )


def _exchange_refresh_token(request: Request) -> Response:
    refresh_token_value = request.data.get("refresh_token", "")
    if not refresh_token_value:
        return Response({"error": "invalid_request", "error_description": "refresh_token is required"}, status=400)

    old_refresh = find_oauth_refresh_token(refresh_token_value)
    if old_refresh is None:
        return Response({"error": "invalid_grant", "error_description": "Invalid or revoked refresh token"}, status=400)

    oauth_app = old_refresh.application
    user = old_refresh.user
    scoped_teams = old_refresh.scoped_teams
    old_access = old_refresh.access_token
    old_scope = old_access.scope if old_access else StripeIntegration.SCOPES

    # Atomically revoke to prevent replay attacks — if another request already revoked it, rows_updated == 0
    rows_updated = OAuthRefreshToken.objects.filter(id=old_refresh.id, revoked__isnull=True).update(
        revoked=timezone.now(), access_token=None
    )
    if rows_updated == 0:
        return Response({"error": "invalid_grant", "error_description": "Invalid or revoked refresh token"}, status=400)

    if old_access:
        old_access.delete()

    new_access_value = generate_random_oauth_access_token(None)
    new_access = OAuthAccessToken.objects.create(
        application=oauth_app,
        token=new_access_value,
        user=user,
        expires=timezone.now() + timedelta(seconds=ACCESS_TOKEN_EXPIRY_SECONDS),
        scope=old_scope,
        scoped_teams=scoped_teams,
    )

    new_refresh_value = generate_random_oauth_refresh_token(None)
    OAuthRefreshToken.objects.create(
        application=oauth_app,
        token=new_refresh_value,
        user=user,
        access_token=new_access,
        scoped_teams=scoped_teams,
    )

    logger.info("stripe_app.token_refresh.success", user_id=user.id)

    return Response(
        {
            "token_type": "bearer",
            "access_token": new_access_value,
            "refresh_token": new_refresh_value,
            "expires_in": ACCESS_TOKEN_EXPIRY_SECONDS,
        }
    )


# ---------------------------------------------------------------------------
# POST /provisioning/resources
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@stripe_region_proxy(strategy="bearer_lookup")
def provisioning_resources_create(request: Request) -> Response:
    auth_error, user, access_token = _authenticate_bearer(request)
    if auth_error:
        return auth_error
    assert access_token is not None

    service_id = request.data.get("service_id", "")
    if service_id and service_id != "posthog_analytics":
        return Response(
            {
                "status": "error",
                "id": "",
                "error": {"code": "unknown_service", "message": f"Unknown service_id: {service_id}"},
            },
            status=400,
        )

    scoped_teams = access_token.scoped_teams or []

    if not scoped_teams:
        return Response(
            {
                "status": "error",
                "id": "",
                "error": {"code": "no_team", "message": "No team associated with this token"},
            },
            status=400,
        )

    team_id = scoped_teams[0]
    try:
        team = Team.objects.get(id=team_id)
    except Team.DoesNotExist:
        logger.warning("stripe_app.resource_create.team_not_found", team_id=team_id)
        capture_exception(Exception("Stripe APP resource create: team not found"))
        return Response(
            {"status": "error", "id": str(team_id), "error": {"code": "team_not_found", "message": "Team not found"}},
            status=404,
        )

    host = _get_instance_host()

    return Response(
        {
            "status": "complete",
            "id": str(team_id),
            "service_id": "posthog_analytics",
            "complete": {
                "access_configuration": {
                    "api_key": team.api_token,
                    "host": host,
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /provisioning/resources/:id
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
@stripe_region_proxy(strategy="bearer_lookup")
def provisioning_resource_detail(request: Request, resource_id: str) -> Response:
    auth_error, user, access_token = _authenticate_bearer(request)
    if auth_error:
        return auth_error
    assert access_token is not None

    scoped_teams = access_token.scoped_teams or []

    try:
        team_id = int(resource_id)
    except (ValueError, TypeError):
        return Response(
            {
                "status": "error",
                "id": resource_id,
                "error": {"code": "invalid_resource_id", "message": "Invalid resource ID"},
            },
            status=400,
        )

    if team_id not in scoped_teams:
        return Response(
            {
                "status": "error",
                "id": resource_id,
                "error": {"code": "forbidden", "message": "Resource not accessible with this token"},
            },
            status=403,
        )

    try:
        team = Team.objects.get(id=team_id)
    except Team.DoesNotExist:
        logger.warning("stripe_app.resource_detail.team_not_found", team_id=team_id)
        capture_exception(Exception("Stripe APP resource detail: team not found"))
        return Response(
            {"status": "error", "id": resource_id, "error": {"code": "not_found", "message": "Resource not found"}},
            status=404,
        )

    host = _get_instance_host()

    return Response(
        {
            "status": "complete",
            "id": resource_id,
            "service_id": "posthog_analytics",
            "complete": {
                "access_configuration": {
                    "api_key": team.api_token,
                    "host": host,
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# POST /provisioning/deep_links
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
@stripe_region_proxy(strategy="bearer_lookup")
def deep_links(request: Request) -> Response:
    auth_error, user, access_token = _authenticate_bearer(request)
    if auth_error:
        return auth_error
    assert access_token is not None

    purpose = request.data.get("purpose", "dashboard")

    scoped_teams = access_token.scoped_teams or []
    team_id = scoped_teams[0] if scoped_teams else None

    host = _get_instance_host()

    token = secrets.token_urlsafe(32)
    cache_key = f"{DEEP_LINK_CACHE_PREFIX}{token}"
    cache.set(
        cache_key,
        {
            "user_id": access_token.user_id,
            "team_id": team_id,
        },
        timeout=DEEP_LINK_TTL_SECONDS,
    )

    expires_at = timezone.now() + timedelta(seconds=DEEP_LINK_TTL_SECONDS)

    url = f"{host}/login/stripe?token={token}"
    if team_id:
        url += f"&team_id={team_id}"

    return Response(
        {
            "purpose": purpose,
            "url": url,
            "expires_at": expires_at.isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _authenticate_bearer(request: Request) -> tuple[Response | None, User | None, OAuthAccessToken | None]:
    auth = StripeProvisioningBearerAuthentication()
    try:
        result = auth.authenticate(request)
    except AuthenticationFailed as e:
        return (
            Response({"status": "error", "error": {"code": "unauthorized", "message": str(e)}}, status=401),
            None,
            None,
        )
    if result is None:
        return (
            Response(
                {"status": "error", "error": {"code": "unauthorized", "message": "Missing bearer token"}}, status=401
            ),
            None,
            None,
        )
    return None, result[0], result[1]


def _get_stripe_oauth_app():
    if settings.STRIPE_POSTHOG_OAUTH_CLIENT_ID:
        try:
            return OAuthApplication.objects.get(client_id=settings.STRIPE_POSTHOG_OAUTH_CLIENT_ID)
        except OAuthApplication.DoesNotExist:
            logger.warning(
                "stripe_app.oauth_app.client_id_not_found",
                client_id=settings.STRIPE_POSTHOG_OAUTH_CLIENT_ID,
            )

    app, _created = OAuthApplication.objects.get_or_create(
        name=STRIPE_APP_NAME,
        defaults={
            "client_id": generate_oauth_client_id(),
            "client_secret": "",
            "client_type": OAuthApplication.CLIENT_CONFIDENTIAL,
            "authorization_grant_type": OAuthApplication.GRANT_AUTHORIZATION_CODE,
            "redirect_uris": "https://localhost",
            "algorithm": "RS256",
        },
    )
    return app


def _get_instance_host() -> str:
    region = get_instance_region() or "US"
    return _region_to_host(region)


def _region_to_host(region: str) -> str:
    region_lower = region.lower()
    if region_lower == "eu":
        return "https://eu.posthog.com"
    elif region_lower in ("us", "dev"):
        return "https://us.posthog.com"
    return settings.SITE_URL
