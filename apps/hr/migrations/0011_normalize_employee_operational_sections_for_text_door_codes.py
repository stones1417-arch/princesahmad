from django.db import migrations


FEMALE_DOOR_CODES = {
    "12",
    "13",
    "14",
    "15",
    "16",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
}


def normalize_employee_operational_sections_for_text_door_codes(apps, schema_editor):
    Employee = apps.get_model("hr", "Employee")
    DoorAssignment = apps.get_model("distribution", "DoorAssignment")

    for employee in Employee.objects.all().iterator():
        door_numbers = {
            str(door_number).strip()
            for door_number in DoorAssignment.objects.filter(employee_id=employee.pk)
            .values_list("door__door_number", flat=True)
            if str(door_number).strip()
        }

        if not door_numbers:
            continue

        has_female_door = bool(door_numbers & FEMALE_DOOR_CODES)
        has_other_door = bool(door_numbers - FEMALE_DOOR_CODES)

        if has_female_door and not has_other_door:
            employee.operational_section = "female"
        elif has_other_door and not has_female_door:
            employee.operational_section = "male"
        else:
            continue

        employee.save(update_fields=["operational_section"])


def reverse_noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("hr", "0010_employee_operational_section"),
        ("distribution", "0006_alter_doorassignment_options"),
        ("locations", "0006_alter_door_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            normalize_employee_operational_sections_for_text_door_codes,
            reverse_noop,
        ),
    ]
