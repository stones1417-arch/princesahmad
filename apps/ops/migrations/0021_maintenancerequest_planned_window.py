from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ops", "0020_incident_door_incident_assigned_to")]

    operations = [
        migrations.AddField(
            model_name="maintenancerequest",
            name="planned_start_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="وقت البدء المخطط"),
        ),
        migrations.AddField(
            model_name="maintenancerequest",
            name="planned_end_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="وقت الانتهاء المخطط"),
        ),
    ]
