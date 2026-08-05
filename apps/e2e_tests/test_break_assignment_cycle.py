from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.breaks.models import Break
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.scheduling.services import activate_shift


class BreakAssignmentCycleE2ETests(TestCase):
    """
    اختبارات End-to-End لقواعد الراحة والتسكين.
    """

    def setUp(self):
        self.operator = create_user(
            username="e2e_break_operator",
            is_staff=True,
            is_active=True,
        )

        self.shift_type = create_shift_type(
            name="وردية اختبار الراحة والتسكين",
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=False,
        )

        self.first_door = create_door(
            door_number=2,
            is_active=True,
        )

        self.second_door = create_door(
            door_number=3,
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف اختبار الراحة والتسكين",
            employee_number="E2E-BRK-1001",
            is_active=True,
            can_work_on_doors=True,
        )

        self.second_employee = create_employee(
            full_name="موظف اختبار ثانٍ",
            employee_number="E2E-BRK-1002",
            is_active=True,
            can_work_on_doors=True,
        )

    def test_employee_cannot_be_assigned_twice_in_same_shift(self):
        """
        لا يمكن تسكين الموظف نفسه على بابين
        داخل الوردية النشطة نفسها.
        """

        active_shift = activate_shift(
            self.shift
        )

        first_assignment = DoorAssignment.objects.create(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.operator,
        )

        self.assertIsNotNone(
            first_assignment.pk
        )

        duplicate_assignment = DoorAssignment(
            shift_plan=active_shift,
            door=self.second_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.operator,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate_assignment.full_clean()

    def test_door_cannot_have_two_active_supervisors(self):
        """
        لا يمكن تعيين مشرفين نشطين
        للباب نفسه داخل الوردية نفسها.
        """

        active_shift = activate_shift(
            self.shift
        )

        first_supervisor = DoorAssignment.objects.create(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_supervisor=True,
            is_active=True,
            assigned_by=self.operator,
        )

        self.assertIsNotNone(
            first_supervisor.pk
        )

        second_supervisor = DoorAssignment(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_supervisor=True,
            is_active=True,
            assigned_by=self.operator,
        )

        with self.assertRaises(
            ValidationError
        ):
            second_supervisor.full_clean()

    def test_inactive_employee_cannot_be_assigned(self):
        """
        لا يمكن تسكين موظف غير نشط.
        """

        active_shift = activate_shift(
            self.shift
        )

        self.employee.work_status = (
            self.employee.WorkStatus.INACTIVE
        )
        self.employee.save()

        assignment = DoorAssignment(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.operator,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_employee_without_door_permission_cannot_be_assigned(self):
        """
        لا يمكن تسكين موظف غير مصرح له
        بالعمل على الأبواب.
        """

        active_shift = activate_shift(
            self.shift
        )

        self.employee.can_work_on_doors = False
        self.employee.save(
            update_fields=[
                "can_work_on_doors",
                "updated_at",
            ]
        )

        assignment = DoorAssignment(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.operator,
        )

        with self.assertRaises(
            ValidationError
        ):
            assignment.full_clean()

    def test_employee_break_is_created_for_shift_type(self):
        """
        يجب إنشاء سجل راحة نشط للموظف
        مرتبط بنوع الوردية.
        """

        break_obj = Break.objects.create(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=True,
            notes="راحة اختبار End-to-End",
        )

        self.assertIsNotNone(
            break_obj.pk
        )

        self.assertTrue(
            break_obj.is_active
        )

        self.assertEqual(
            break_obj.employee_id,
            self.employee.pk,
        )

        self.assertEqual(
            break_obj.shift_type_id,
            self.shift_type.pk,
        )

    def test_inactive_break_does_not_block_assignment(self):
        """
        سجل الراحة غير النشط لا يمنع التسكين.
        """

        Break.objects.create(
            employee=self.employee,
            shift_type=self.shift_type,
            job_title=Break.BreakJobTitle.MONITOR,
            rest_days=Break.RestDays.FRIDAY_SATURDAY,
            is_active=False,
            notes="راحة قديمة غير نشطة",
        )

        active_shift = activate_shift(
            self.shift
        )

        assignment = DoorAssignment.objects.create(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.operator,
        )

        self.assertIsNotNone(
            assignment.pk
        )

    def test_different_employees_can_be_assigned_to_same_door(self):
        """
        يسمح بتسكين موظفين مختلفين على الباب نفسه
        ما دام أحدهما فقط مشرفًا.
        """

        active_shift = activate_shift(
            self.shift
        )

        supervisor = DoorAssignment.objects.create(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.employee,
            role=DoorAssignment.Role.SUPERVISOR,
            is_supervisor=True,
            is_active=True,
            assigned_by=self.operator,
        )

        monitor = DoorAssignment.objects.create(
            shift_plan=active_shift,
            door=self.first_door,
            employee=self.second_employee,
            role=DoorAssignment.Role.MONITOR,
            is_supervisor=False,
            is_active=True,
            assigned_by=self.operator,
        )

        self.assertIsNotNone(
            supervisor.pk
        )

        self.assertIsNotNone(
            monitor.pk
        )

        self.assertEqual(
            DoorAssignment.objects.filter(
                shift_plan=active_shift,
                door=self.first_door,
                is_active=True,
            ).count(),
            2,
        )