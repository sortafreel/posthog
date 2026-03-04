from datetime import timedelta

from django.utils import timezone

from posthog.models.oauth import OAuthAccessToken
from posthog.models.team.team import Team

from ee.api.agentic_provisioning.test.base import StripeProvisioningTestBase


class TestProvisioningResources(StripeProvisioningTestBase):
    def test_create_resource_returns_complete(self):
        token = self._get_bearer_token()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources",
            data={"service_id": "posthog_analytics"},
            token=token,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complete"
        assert data["id"] == str(self.team.id)
        assert "api_key" in data["complete"]["access_configuration"]
        assert "host" in data["complete"]["access_configuration"]

    def test_get_resource_returns_complete(self):
        token = self._get_bearer_token()
        res = self._get_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{self.team.id}",
            token=token,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complete"
        assert data["id"] == str(self.team.id)

    def test_get_resource_wrong_team_returns_403(self):
        token = self._get_bearer_token()
        res = self._get_signed_with_bearer(
            "/api/agentic/provisioning/resources/99999",
            token=token,
        )
        assert res.status_code == 403

    def test_get_resource_invalid_id_returns_400(self):
        token = self._get_bearer_token()
        res = self._get_signed_with_bearer(
            "/api/agentic/provisioning/resources/not-a-number",
            token=token,
        )
        assert res.status_code == 400

    def test_create_resource_missing_bearer_returns_401(self):
        res = self._post_signed("/api/agentic/provisioning/resources", data={"service_id": "posthog_analytics"})
        assert res.status_code == 401

    def test_create_resource_invalid_bearer_returns_401(self):
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources",
            data={"service_id": "posthog_analytics"},
            token="pha_invalid_token",
        )
        assert res.status_code == 401

    def test_get_resource_missing_bearer_returns_401(self):
        res = self._get_signed(f"/api/agentic/provisioning/resources/{self.team.id}")
        assert res.status_code == 401

    def test_create_resource_empty_scoped_teams_returns_400(self):
        token = self._get_bearer_token()
        access_token = OAuthAccessToken.objects.get(token=token)
        access_token.scoped_teams = []
        access_token.save(update_fields=["scoped_teams"])
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources",
            data={"service_id": "posthog_analytics"},
            token=token,
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "no_team"

    def test_create_resource_deleted_team_returns_404(self):
        token = self._get_bearer_token()
        team_id = self.team.id
        Team.objects.filter(id=team_id).delete()
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources",
            data={"service_id": "posthog_analytics"},
            token=token,
        )
        assert res.status_code == 404

    def test_get_resource_deleted_team_returns_404(self):
        token = self._get_bearer_token()
        team_id = self.team.id
        access_token = OAuthAccessToken.objects.get(token=token)
        access_token.scoped_teams = [team_id]
        access_token.save(update_fields=["scoped_teams"])
        Team.objects.filter(id=team_id).delete()
        res = self._get_signed_with_bearer(
            f"/api/agentic/provisioning/resources/{team_id}",
            token=token,
        )
        assert res.status_code == 404

    def test_expired_bearer_returns_401(self):
        token = self._get_bearer_token()
        access_token = OAuthAccessToken.objects.get(token=token)
        access_token.expires = timezone.now() - timedelta(hours=1)
        access_token.save(update_fields=["expires"])
        res = self._post_signed_with_bearer(
            "/api/agentic/provisioning/resources",
            data={"service_id": "posthog_analytics"},
            token=token,
        )
        assert res.status_code == 401
