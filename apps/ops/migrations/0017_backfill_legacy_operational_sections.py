from django.db import migrations


def backfill_legacy_operational_sections(apps, schema_editor):
    Door = apps.get_model("locations", "Door")
    DoorAssignment = apps.get_model("distribution", "DoorAssignment")
    DoorShift = apps.get_model("ops", "DoorShift")
    Incident = apps.get_model("ops", "Incident")
    MaintenanceRequest = apps.get_model("ops", "MaintenanceRequest")

    for section in ("male", "female"):
        door_numbers = Door.objects.filter(
            operational_section=section,
        ).values("door_number")

        DoorAssignment.objects.filter(
            door__operational_section=section,
        ).exclude(section=section).update(section=section)

        DoorShift.objects.filter(
            section="",
            door_number__in=door_numbers,
        ).update(section=section)

    for section in ("male", "female"):
        MaintenanceRequest.objects.filter(
            section="",
            assignment__section=section,
        ).update(section=section)
        Incident.objects.filter(
            section="",
            assignment__section=section,
        ).update(section=section)

        MaintenanceRequest.objects.filter(
            section="",
            door_shift__section=section,
        ).update(section=section)
        Incident.objects.filter(
            section="",
            door_shift__section=section,
        ).update(section=section)


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0016_doorshift_section_incident_assignment_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_legacy_operational_sections,
            migrations.RunPython.noop,
        ),
    ]