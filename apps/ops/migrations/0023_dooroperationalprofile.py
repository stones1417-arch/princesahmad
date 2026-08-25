from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0006_alter_door_options_and_more"),
        ("ops", "0022_incident_escalated_at_incident_escalated_by_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DoorOperationalProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "target_staff_count",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[MinValueValidator(1)],
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "door",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="operational_profile",
                        to="locations.door",
                    ),
                ),
            ],
            options={
                "verbose_name": "ملف التشغيل للباب",
                "verbose_name_plural": "ملفات التشغيل للأبواب",
                "ordering": ["door__sort_order", "door__door_number"],
            },
        ),
    ]
