from django.db import migrations


def _normalize_text_code(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_legacy_operational_sections_for_text_door_codes(apps, schema_editor):
    Door = apps.get_model("locations", "Door")
    DoorShift = apps.get_model("ops", "DoorShift")
    Incident = apps.get_model("ops", "Incident")
    MaintenanceRequest = apps.get_model("ops", "MaintenanceRequest")

    for section in ("male", "female"):
        door_codes = {
            _normalize_text_code(value)
            for value in Door.objects.filter(
                operational_section=section,
            ).values_list("door_number", flat=True)
            if _normalize_text_code(value)
        }

        if not door_codes:
            continue

        for record in DoorShift.objects.filter(
            section="",
            door_number__in=sorted(door_codes),
        ).iterator():
            code = _normalize_text_code(record.door_number)
            if code in door_codes:
                record.section = section
                record.save(update_fields=["section"])

        for model in (MaintenanceRequest, Incident):
            model.objects.filter(
                section="",
                assignment__section=section,
            ).update(section=section)
            model.objects.filter(
                section="",
                door_shift__section=section,
            ).update(section=section)


def reverse_noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0006_alter_door_options_and_more"),
        ("ops", "0018_alter_doorshift_options_doorshift_sort_order_and_more"),
    ]

    operations = [
        migrations.RunPython(
            normalize_legacy_operational_sections_for_text_door_codes,
            reverse_noop,
        ),
    ]
