from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import create_door, create_employee, create_shift_plan, create_shift_type
from apps.distribution.models import DoorAssignment

populate_operational_sections = import_module(
    "apps.hr.migrations.0010_employee_operational_section"
).populate_operational_sections


def get_historical_apps_for_0010():
    executor = MigrationExecutor(connection)
    return executor.loader.project_state(
        nodes=[
            ("hr", "0009_alter_employee_options_employee_gender_and_more"),
            ("distribution", "0006_alter_doorassignment_options"),
            ("locations", "0004_alter_door_options_and_more"),
        ]
    ).apps


class OperationalSectionBackfillTests(TestCase):
    def setUp(self):
        self.shift_plan = create_shift_plan(
            shift_type=create_shift_type(),
            is_active=True,
        )
        self.other_shift_plan = create_shift_plan(
            shift_type=self.shift_plan.shift_type,
            shift_date=timezone.localdate() + timedelta(days=1),
            is_active=True,
        )
        self.male_door = create_door(door_number=1)
        self.female_door = create_door(door_number=12)

    def _assign(self, employee, door, shift_plan=None):
        DoorAssignment.objects.create(
            shift_plan=shift_plan or self.shift_plan,
            employee=employee,
            door=door,
            role=DoorAssignment.Role.MONITOR,
        )

    def test_backfill_only_classifies_exclusive_door_evidence(self):
        male_employee = create_employee(
            employee_number="BACKFILL-MALE",
            operational_section=None,
        )
        female_employee = create_employee(
            employee_number="BACKFILL-FEMALE",
            operational_section=None,
        )
        conflict_employee = create_employee(
            employee_number="BACKFILL-CONFLICT",
            operational_section=None,
        )
        unassigned_employee = create_employee(
            employee_number="BACKFILL-NONE",
            operational_section=None,
        )

        self._assign(male_employee, self.male_door)
        self._assign(female_employee, self.female_door)
        self._assign(conflict_employee, self.male_door)
        self._assign(
            conflict_employee,
            self.female_door,
            self.other_shift_plan,
        )

        historical_apps = get_historical_apps_for_0010()
        real_get_model = historical_apps.get_model
        door_numbers_by_employee = {
            male_employee.pk: [1],
            female_employee.pk: [12],
            conflict_employee.pk: [1, 12],
            unassigned_employee.pk: [],
        }

        def fake_get_model(app_label, model_name):
            if app_label == "distribution" and model_name == "DoorAssignment":
                class FakeDoorAssignment:
                    class _Manager:
                        @staticmethod
                        def filter(**kwargs):
                            employee_id = kwargs.get("employee_id")
                            values = door_numbers_by_employee.get(employee_id, [])
                            return SimpleNamespace(
                                values_list=lambda *args, **kwargs: values,
                            )

                    objects = _Manager()

                return FakeDoorAssignment
            return real_get_model(app_label, model_name)

        with patch.object(historical_apps, "get_model", side_effect=fake_get_model):
            populate_operational_sections(historical_apps, None)

        male_employee.refresh_from_db()
        female_employee.refresh_from_db()
        conflict_employee.refresh_from_db()
        unassigned_employee.refresh_from_db()

        self.assertEqual(male_employee.operational_section, "male")
        self.assertEqual(female_employee.operational_section, "female")
        self.assertIsNone(conflict_employee.operational_section)
        self.assertIsNone(unassigned_employee.operational_section)