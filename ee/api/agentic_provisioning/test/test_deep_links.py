from django.test import override_settings

from ee.api.agentic_provisioning.test.base import HMAC_SECRET, StripeProvisioningTestBase


@override_settings(STRIPE_APP_SECRET_KEY=HMAC_SECRET)
class TestDeepLinks(StripeProvisioningTestBase):
    def test_deep_link_returns_url(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/deep_links",
            data={"purpose": "dashboard"},
            token=token,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["purpose"] == "dashboard"
        assert "url" in data
        assert "expires_at" in data
        assert "token=" in data["url"]

    def test_deep_link_url_contains_team_id(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/deep_links",
            data={"purpose": "dashboard"},
            token=token,
        )
        url = res.json()["url"]
        assert f"team_id={self.team.id}" in url

    def test_deep_link_missing_bearer_returns_401(self):
        res = self._post_signed("/api/agentic/provisioning/deep_links", data={"purpose": "dashboard"})
        assert res.status_code == 401

    def test_deep_link_default_purpose(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/deep_links",
            data={},
            token=token,
        )
        assert res.status_code == 200
        assert res.json()["purpose"] == "dashboard"
