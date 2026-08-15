from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment
from apps.distribution.services import DistributionService
from apps.scheduling.models import ShiftPlan


class DoorAssignmentConflictTests(TestCase):
    """
    اختبارات تعارضات التوزيع.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية تعارض توزيع",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        self.first_door = create_door(
            door_number=10,
        )

        self.second_door = create_door(
            door_number=11,
        )

        self.first_employee = create_employee(
            full_name="الموظف الأول",
            employee_number="82001",
            operational_section="male",
        )

        self.second_employee = create_employee(
            full_name="الموظف الثاني",
            employee_number="82002",
            operational_section="male",
        )

    def test_employee_cannot_be_assigned_twice_in_same_shift(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        duplicate_assignment = DoorAssignment(
            shift_plan=self.shift,
            door=self.second_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate_assignment.full_clean()

    def test_same_day_non_overlapping_shifts_are_allowed(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية صباحية قانونية",
                start_time=time(8, 0),
                end_time=time(12, 0),
            ),
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(12, 0),
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية مسائية قانونية",
                start_time=time(12, 0),
                end_time=time(16, 0),
            ),
            date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DistributionService.validate_assignment(
            shift_plan=second_shift,
            employee=self.first_employee,
            door=self.second_door,
            role=DoorAssignment.Role.MONITOR,
        )

    def test_exact_boundary_end_equals_next_start_is_allowed(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية حدها 12",
                start_time=time(8, 0),
                end_time=time(12, 0),
            ),
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(12, 0),
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية تبدأ عند 12",
                start_time=time(12, 0),
                end_time=time(16, 0),
            ),
            date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DistributionService.validate_assignment(
            shift_plan=second_shift,
            employee=self.first_employee,
            door=self.second_door,
            role=DoorAssignment.Role.MONITOR,
        )

    def test_cross_midnight_overlap_is_rejected(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية ليلية سابقة",
                start_time=time(21, 0),
                end_time=time(2, 0),
            ),
            date=timezone.localdate(),
            start_time=time(21, 0),
            end_time=time(2, 0),
            crosses_midnight=True,
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية ليلية لاحقة",
                start_time=time(1, 0),
                end_time=time(7, 0),
            ),
            date=timezone.localdate() + timezone.timedelta(days=1),
            start_time=time(1, 0),
            end_time=time(7, 0),
            crosses_midnight=False,
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            DistributionService.validate_assignment(
                shift_plan=second_shift,
                employee=self.first_employee,
                door=self.second_door,
                role=DoorAssignment.Role.MONITOR,
            )

    def test_cross_midnight_boundary_without_overlap_is_allowed(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية ليلية حدودية",
                start_time=time(21, 0),
                end_time=time(2, 0),
            ),
            date=timezone.localdate(),
            start_time=time(21, 0),
            end_time=time(2, 0),
            crosses_midnight=True,
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية فجر بعد الحد",
                start_time=time(2, 0),
                end_time=time(8, 0),
            ),
            date=timezone.localdate() + timezone.timedelta(days=1),
            start_time=time(2, 0),
            end_time=time(8, 0),
            crosses_midnight=False,
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DistributionService.validate_assignment(
            shift_plan=second_shift,
            employee=self.first_employee,
            door=self.second_door,
            role=DoorAssignment.Role.MONITOR,
        )

    def test_different_employees_on_overlapping_shifts_are_allowed(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية متداخلة موظف أول",
                start_time=time(8, 0),
                end_time=time(16, 0),
            ),
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية متداخلة موظف ثان",
                start_time=time(15, 0),
                end_time=time(21, 0),
            ),
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(21, 0),
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DistributionService.validate_assignment(
            shift_plan=second_shift,
            employee=self.second_employee,
            door=self.second_door,
            role=DoorAssignment.Role.MONITOR,
        )

    def test_current_assignment_does_not_conflict_with_itself_when_updating(self):
        assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        DistributionService.validate_assignment(
            shift_plan=self.shift,
            employee=self.first_employee,
            door=self.second_door,
            role=DoorAssignment.Role.MONITOR,
            exclude_pk=assignment.pk,
        )

    def test_auto_assign_cannot_bypass_employee_time_conflict(self):
        employee = create_employee(
            full_name="موظف منع التوزيع الآلي",
            employee_number="82010",
            operational_section="male",
            is_active=True,
            can_work_on_doors=True,
        )

        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية أولى منع تلقائي",
                start_time=time(8, 0),
                end_time=time(16, 0),
            ),
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )
        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية ثانية منع تلقائي",
                start_time=time(15, 0),
                end_time=time(21, 0),
            ),
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(21, 0),
            is_active=True,
            is_finished=False,
        )
        ShiftPlan.objects.bulk_create([first_shift, second_shift])

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        result = DistributionService.auto_assign(
            shift_plan=second_shift,
            limit=10,
        )

        self.assertNotIn(employee, [item.employee for item in result["created"]])

    def test_employee_cannot_be_assigned_in_overlapping_shift_times(self):
        first_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية أولى متداخلة",
                start_time=time(8, 0),
                end_time=time(16, 0),
            ),
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية ثانية متداخلة",
                start_time=time(15, 0),
                end_time=time(21, 0),
            ),
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(21, 0),
            is_active=True,
            is_finished=False,
        )

        ShiftPlan.objects.bulk_create(
            [
                first_shift,
                second_shift,
            ]
        )

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError,
        ):
            DistributionService.validate_assignment(
                shift_plan=second_shift,
                employee=self.first_employee,
                door=self.second_door,
                role=DoorAssignment.Role.MONITOR,
            )

    def test_employee_overlap_validation_uses_shift_type_fallback_time_ranges(self):
        fallback_type = create_shift_type(
            name="وردية افتراضية متداخلة",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        first_shift = ShiftPlan(
            shift_type=fallback_type,
            date=timezone.localdate(),
            start_time=None,
            end_time=None,
            is_active=True,
            is_finished=False,
        )

        second_shift = ShiftPlan(
            shift_type=create_shift_type(
                name="وردية لاحقة متداخلة",
                start_time=time(15, 0),
                end_time=time(21, 0),
            ),
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(21, 0),
            is_active=True,
            is_finished=False,
        )

        ShiftPlan.objects.bulk_create(
            [
                first_shift,
                second_shift,
            ]
        )

        DoorAssignment.objects.create(
            shift_plan=first_shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError,
        ):
            DistributionService.validate_assignment(
                shift_plan=second_shift,
                employee=self.first_employee,
                door=self.second_door,
                role=DoorAssignment.Role.MONITOR,
            )

    def test_database_rejects_duplicate_active_employee_assignment(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        with self.assertRaises(
            (
                ValidationError,
                IntegrityError,
            )
        ):
            with transaction.atomic():
                DoorAssignment.objects.create(
                    shift_plan=self.shift,
                    door=self.second_door,
                    employee=self.first_employee,
                    role=DoorAssignment.Role.MONITOR,
                    is_active=True,
                )

    def test_door_cannot_have_two_active_supervisors(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        second_supervisor = DoorAssignment(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            second_supervisor.full_clean()

    def test_inactive_old_assignment_does_not_block_new_assignment(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=False,
        )

        new_assignment = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.second_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
        )

        self.assertIsNotNone(
            new_assignment.pk
        )

    def test_inactive_supervisor_does_not_block_new_supervisor(self):
        DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.first_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=False,
        )

        new_supervisor = DoorAssignment.objects.create(
            shift_plan=self.shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_active=True,
        )

        self.assertTrue(
            new_supervisor.is_supervisor
        )

    def test_section_doors_accept_one_supervisor_per_section(self):
        male_door = create_door(
            door_number="6A",
        )
        female_door = create_door(
            door_number="12",
        )
        male_supervisor = create_employee(
            full_name="مشرف الباب الرجالي",
            employee_number="82003",
            operational_section="male",
        )
        female_supervisor = create_employee(
            full_name="مشرفة الباب النسائي",
            employee_number="82004",
            operational_section="female",
        )

        DistributionService.create_assignment(
            shift_plan=self.shift,
            door=male_door,
            employee=male_supervisor,
            role=DoorAssignment.Role.SUPERVISOR,
        )
        female_assignment = DistributionService.create_assignment(
            shift_plan=self.shift,
            door=female_door,
            employee=female_supervisor,
            role=DoorAssignment.Role.SUPERVISOR,
        )

        self.assertEqual(female_assignment.section, "female")