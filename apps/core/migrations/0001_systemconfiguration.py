from django.db import migrations, models
import django.core.validators


def create_singleton(apps, schema_editor):
    configuration = apps.get_model("core", "SystemConfiguration")
    configuration.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SystemConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization_name", models.CharField(default="إدارة الأبواب", max_length=180)),
                ("platform_name", models.CharField(default="منصة أبواب", max_length=120)),
                ("timezone", models.CharField(default="Asia/Riyadh", max_length=64)),
                ("default_language", models.CharField(choices=[("ar", "العربية"), ("en", "English")], default="ar", max_length=5)),
                ("support_email", models.EmailField(blank=True, max_length=254)),
                ("support_phone", models.CharField(blank=True, max_length=24, validators=[django.core.validators.RegexValidator(message="أدخل رقم تواصل صحيحًا.", regex="^\\+?[0-9 ()-]{7,24}$")])),
                ("communications_enabled", models.BooleanField(default=True)),
                ("email_notifications_enabled", models.BooleanField(default=True)),
                ("sms_notifications_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "إعدادات النظام", "verbose_name_plural": "إعدادات النظام"},
        ),
        migrations.AddConstraint(
            model_name="systemconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(("pk", 1)),
                name="core_systemconfiguration_singleton_pk",
            ),
        ),
        migrations.RunPython(create_singleton, migrations.RunPython.noop),
    ]
