from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase


class StaticFilesConfigurationTests(SimpleTestCase):
    def test_whitenoise_is_enabled_after_security_middleware(self):
        security_index = settings.MIDDLEWARE.index(
            "django.middleware.security.SecurityMiddleware"
        )
        whitenoise_index = settings.MIDDLEWARE.index(
            "whitenoise.middleware.WhiteNoiseMiddleware"
        )

        self.assertEqual(whitenoise_index, security_index + 1)

    def test_development_static_files_use_finders(self):
        self.assertTrue(settings.WHITENOISE_AUTOREFRESH)
        self.assertTrue(settings.WHITENOISE_USE_FINDERS)
        self.assertEqual(settings.WHITENOISE_MAX_AGE, 31536000)