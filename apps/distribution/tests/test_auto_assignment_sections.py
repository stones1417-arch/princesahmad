from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.distribution.services import DistributionService
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.notifications.models import Notification


class AutomaticAssignmentSectionTests(TestCase):
    def setUp(self):
        shift_type = create_shift_type(
            name="وردية التوزيع حسب القسم",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )
        self.shift_plan = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.shared_door = create_door(
            door_number=17,
        )
        Door.objects.exclude(
            pk=self.shared_door.pk,
        ).update(is_active=False)

    def test_auto_assign_keeps_male_and_female_assignments_separate_on_shared_door(self):
        male_employee = create_employee(
            full_name="موظف رجالي آلي",
            employee_number="91001",
            operational_section="male",
        )
        female_employee = create_employee(
            full_name="موظفة نسائية آلية",
            employee_number="91002",
            operational_section="female",
        )

        male_result = DistributionService.auto_assign(
            shift_plan=self.shift_plan,
            limit=1,
        )
        female_result = DistributionService.auto_assign(
            shift_plan=self.shift_plan,
            limit=1,
        )

        self.assertEqual(
            male_result["created"][0].employee_id,
            male_employee.id,
        )
        self.assertEqual(
            female_result["created"][0].employee_id,
            female_employee.id,
        )
        self.assertSetEqual(
            set(
                DoorAssignment.objects.values_list(
                    "section",
                    flat=True,
                )
            ),
            {
                DoorAssignment.AssignmentSection.MALE,
                DoorAssignment.AssignmentSection.FEMALE,
            },
        )
        self.assertEqual(
            DoorAssignment.objects.values(
                "door_id",
            ).distinct().count(),
            1,
        )

    def test_auto_assign_never_selects_a_door_from_the_other_section(self):
        male_door = create_door(
            door_number=1,
        )
        female_door = create_door(
            door_number=12,
        )
        Door.objects.exclude(
            pk__in=[male_door.pk, female_door.pk],
        ).update(is_active=False)

        male_employee = create_employee(
            full_name="موظف رجالي مقيد",
            employee_number="91003",
            operational_section="male",
        )
        female_employee = create_employee(
            full_name="موظفة نسائية مقيدة",
            employee_number="91004",
            operational_section="female",
        )

        DistributionService.auto_assign(
            shift_plan=self.shift_plan,
            limit=1,
        )
        DistributionService.auto_assign(
            shift_plan=self.shift_plan,
            limit=1,
        )

        assignments = DoorAssignment.objects.select_related(
            "employee",
            "door",
        )
        self.assertEqual(
            assignments.get(employee=male_employee).door_id,
            male_door.id,
        )
        self.assertEqual(
            assignments.get(employee=female_employee).door_id,
            female_door.id,
        )

    def test_assignment_notification_stays_with_its_operational_section(self):
        male_user = create_user(username="assignment-notice-male")
        female_user = create_user(username="assignment-notice-female")
        male_employee = create_employee(
            full_name="موظف تكليف رجالي",
            employee_number="91005",
            operational_section="male",
            user=male_user,
        )
        female_employee = create_employee(
            full_name="موظفة تكليف نسائية",
            employee_number="91006",
            operational_section="female",
            user=female_user,
        )

        DistributionService.create_assignment(
            shift_plan=self.shift_plan,
            employee=female_employee,
            door=self.shared_door,
            role=DoorAssignment.Role.MONITOR,
        )

        self.assertFalse(Notification.objects.filter(user=male_user).exists())
        notification = Notification.objects.get(user=female_user)
        self.assertEqual(notification.section, Notification.OperationalSection.FEMALE)
        self.assertIn("الحالة: تم الإرسال", notification.message)

        DistributionService.create_assignment(
            shift_plan=self.shift_plan,
            employee=male_employee,
            door=self.shared_door,
            role=DoorAssignment.Role.MONITOR,
        )

        self.assertTrue(Notification.objects.filter(user=male_user).exists())
        self.assertEqual(
            Notification.objects.filter(user=female_user).count(),
            1,
        )

    def test_auto_assign_allows_supervisors_from_both_sections_on_shared_door(self):
        male_supervisor = create_employee(
            full_name="مشرف رجالي مشترك",
            employee_number="91006",
            operational_section="male",
            job_title=Employee.JobTitle.FAJR_SUPERVISOR,
        )
        female_supervisor = create_employee(
            full_name="مشرفة نسائية مشتركة",
            employee_number="91007",
            operational_section="female",
            job_title=Employee.JobTitle.FAJR_SUPERVISOR,
        )
        DistributionService.create_assignment(
            shift_plan=self.shift_plan,
            employee=male_supervisor,
            door=self.shared_door,
            role=DoorAssignment.Role.SUPERVISOR,
        )

        result = DistributionService.auto_assign(
            shift_plan=self.shift_plan,
            limit=1,
        )

        self.assertEqual(result["created"][0].employee_id, female_supervisor.id)
        self.assertEqual(result["created"][0].door_id, self.shared_door.id)

    def test_unclassified_employee_is_not_eligible_for_auto_assignment(self):
        employee = create_employee(
            full_name="موظف غير مصنف",
            employee_number="91008",
            operational_section=None,
        )

        eligible_employees = DistributionService.eligible_employees(
            shift_plan=self.shift_plan,
        )

        self.assertNotIn(employee, eligible_employees)
