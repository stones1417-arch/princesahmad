from django.apps import AppConfig


class E2ETestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.e2e_tests"
    verbose_name = "اختبارات التكامل الشامل"