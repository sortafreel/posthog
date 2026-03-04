from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from posthog.models.oauth import OAuthAccessToken, OAuthApplication
from posthog.models.utils import generate_random_oauth_access_token

from ee.api.agentic_provisioning.test.base import HMAC_SECRET, StripeProvisioningTestBase


@override_settings(STRIPE_APP_SECRET_KEY=HMAC_SECRET)
class TestBearerAuthentication(StripeProvisioningTestBase):
    def test_expired_token_returns_401(self):
        token = self._get_bearer_token()
        access_token = OAuthAccessToken.objects.get(token=token)
        access_token.expires = timezone.now() - timedelta(hours=1)
        access_token.save(update_fields=["expires"])

        res = self._get_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}",
            token=token,
        )
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "unauthorized"

    def test_token_from_non_stripe_app_returns_401(self):
        other_app = OAuthApplication.objects.create(
            name="Not Stripe",
            client_id="other_client_id",
            client_secret="",
            client_type=OAuthApplication.CLIENT_CONFIDENTIAL,
            authorization_grant_type=OAuthApplication.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://localhost",
            algorithm="RS256",
        )
        token_value = generate_random_oauth_access_token(None)
        OAuthAccessToken.objects.create(
            application=other_app,
            token=token_value,
            user=self.user,
            expires=timezone.now() + timedelta(days=1),
            scope="query:read",
            scoped_teams=[self.team.id],
        )

        res = self._get_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}",
            token=token_value,
        )
        assert res.status_code == 401

    def test_missing_authorization_header_returns_401(self):
        res = self._get_signed(f"/api/agentic/provisioning/resources/{self.team.id}")
        assert res.status_code == 401

    def test_non_bearer_auth_scheme_returns_401(self):
        import time

        from ee.api.agentic_provisioning.signature import compute_signature

        body = b""
        ts = int(time.time())
        sig = compute_signature(HMAC_SECRET, ts, body)
        res = self.client.get(
            f"/api/agentic/provisioning/resources/{self.team.id}",
            HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}",
            HTTP_API_VERSION="0.1d",
            HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz",
        )
        assert res.status_code == 401
