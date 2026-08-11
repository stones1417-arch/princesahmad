from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.notification_service import NotificationService
from apps.distribution.models import DoorAssignment
from apps.hr.models import Employee
from apps.notifications.models import Notification


User = get_user_model()


class NotificationServiceSectionTests(TestCase):
    def setUp(self):
        self.male_user = User.objects.create_user(
            username="notification-section-male",
            password="StrongPassword123!",
        )
        self.female_user = User.objects.create_user(
            username="notification-section-female",
            password="StrongPassword123!",
        )
        Employee.objects.create(
            user=self.male_user,
            employee_number="93001",
            full_name="موظف رجالي",
            operational_section=Employee.OperationalSection.MALE,
        )
        Employee.objects.create(
            user=self.female_user,
            employee_number="93002",
            full_name="موظفة نسائية",
            operational_section=Employee.OperationalSection.FEMALE,
        )

    def test_section_notification_does_not_reach_other_section(self):
        NotificationService.info(
            title="تكليف نسائي",
            message="تكليف على باب مشترك.",
            users=[self.male_user, self.female_user],
            section=Notification.OperationalSection.FEMALE,
        )

        self.assertFalse(
            Notification.objects.filter(user=self.male_user).exists()
        )
        self.assertEqual(
            Notification.objects.get(user=self.female_user).section,
            Notification.OperationalSection.FEMALE,
        )

    def test_assignment_section_overrides_manual_section(self):
        assignment = DoorAssignment(section=DoorAssignment.AssignmentSection.FEMALE)

        NotificationService.info(
            title="تكليف",
            message="تكليف مستخرج من التسكين.",
            user=self.female_user,
            section=Notification.OperationalSection.MALE,
            assignment=assignment,
        )

        notification = Notification.objects.get(user=self.female_user)
        self.assertEqual(
            notification.section,
            Notification.OperationalSection.FEMALE,
        )