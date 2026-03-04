from django.conf import settings
from django.test import TestCase, override_settings

from parameterized import parameterized

from ee.api.agentic_provisioning.views import _region_to_host


class TestRegionToHost(TestCase):
    @parameterized.expand(
        [
            ("eu_lower", "eu", "https://eu.posthog.com"),
            ("eu_upper", "EU", "https://eu.posthog.com"),
            ("us_lower", "us", "https://us.posthog.com"),
            ("us_upper", "US", "https://us.posthog.com"),
            ("dev", "dev", "https://us.posthog.com"),
            ("unknown", "ap", settings.SITE_URL),
            ("empty", "", settings.SITE_URL),
        ]
    )
    def test_region_to_host(self, _name, region, expected):
        assert _region_to_host(region) == expected


@override_settings(STRIPE_APP_SECRET_KEY="test_secret", STRIPE_POSTHOG_OAUTH_CLIENT_ID="")
class TestGetStripeOAuthApp(TestCase):
    def test_creates_app_if_none_exists(self):
        from posthog.models.oauth import OAuthApplication

        from ee.api.agentic_provisioning import STRIPE_APP_NAME
        from ee.api.agentic_provisioning.views import _get_stripe_oauth_app

        OAuthApplication.objects.filter(name=STRIPE_APP_NAME).delete()
        app = _get_stripe_oauth_app()
        assert app is not None
        assert app.name == STRIPE_APP_NAME
        assert app.client_id

    def test_returns_existing_app_by_name(self):
        from ee.api.agentic_provisioning import STRIPE_APP_NAME
        from ee.api.agentic_provisioning.views import _get_stripe_oauth_app

        app1 = _get_stripe_oauth_app()
        app2 = _get_stripe_oauth_app()
        assert app1.id == app2.id
        assert app1.name == STRIPE_APP_NAME

    @override_settings(STRIPE_POSTHOG_OAUTH_CLIENT_ID="custom_client_id")
    def test_returns_app_by_client_id_setting(self):
        from posthog.models.oauth import OAuthApplication

        from ee.api.agentic_provisioning.views import _get_stripe_oauth_app

        app = OAuthApplication.objects.create(
            name="Custom Stripe App",
            client_id="custom_client_id",
            client_secret="",
            client_type=OAuthApplication.CLIENT_CONFIDENTIAL,
            authorization_grant_type=OAuthApplication.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://localhost",
            algorithm="RS256",
        )
        result = _get_stripe_oauth_app()
        assert result.id == app.id
        assert result.client_id == "custom_client_id"

    @override_settings(STRIPE_POSTHOG_OAUTH_CLIENT_ID="nonexistent_client_id")
    def test_falls_through_when_client_id_not_found(self):
        from ee.api.agentic_provisioning import STRIPE_APP_NAME
        from ee.api.agentic_provisioning.views import _get_stripe_oauth_app

        app = _get_stripe_oauth_app()
        assert app.name == STRIPE_APP_NAME
