from __future__ import annotations

from django.test import TestCase, override_settings


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    ALLOWED_HOSTS=["localhost"],
)
class ProductionHttpsTests(TestCase):
    def test_http_request_redirects_to_https(self):
        response = self.client.get("/health/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://localhost/health/")

    def test_https_health_check_is_ready_and_sets_hsts(self):
        response = self.client.get(
            "/health/",
            HTTP_HOST="localhost",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            response["Strict-Transport-Security"],
            "max-age=31536000",
        )