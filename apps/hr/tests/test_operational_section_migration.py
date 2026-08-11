from importlib import import_module

from django.apps import apps as django_apps
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import create_door, create_employee, create_shift_plan, create_shift_type
from apps.distribution.models import DoorAssignment


populate_operational_sections = import_module(
    "apps.hr.migrations.0010_employee_operational_section"
).populate_operational_sections


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

        populate_operational_sections(django_apps, None)

        male_employee.refresh_from_db()
        female_employee.refresh_from_db()
        conflict_employee.refresh_from_db()
        unassigned_employee.refresh_from_db()

        self.assertEqual(male_employee.operational_section, "male")
        self.assertEqual(female_employee.operational_section, "female")
        self.assertIsNone(conflict_employee.operational_section)
        self.assertIsNone(unassigned_employee.operational_section)