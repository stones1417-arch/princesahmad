from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0006_alter_door_options_and_more"),
        ("ops", "0019_normalize_legacy_operational_sections_for_text_door_codes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_operational_incidents",
                to=settings.AUTH_USER_MODEL,
                verbose_name="محول إلى",
            ),
        ),
        migrations.AddField(
            model_name="incident",
            name="door",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="incidents",
                to="locations.door",
                verbose_name="الباب المرتبط",
            ),
        ),
    ]
