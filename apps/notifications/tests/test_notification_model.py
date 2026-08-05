from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification


User = get_user_model()


class NotificationModelTests(TestCase):
    """
    اختبارات نموذج الإشعارات.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="notification_model_user",
            email="notification-model@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

    def create_notification(
        self,
        **overrides,
    ) -> Notification:
        data = {
            "user": self.user,
            "title": "إشعار اختباري",
            "message": "هذه رسالة إشعار للاختبار.",
            "level": Notification.Level.INFO,
            "url": "/notifications/",
            "is_read": False,
        }

        data.update(overrides)

        return Notification.objects.create(
            **data
        )

    def test_notification_can_be_created(self):
        """
        يجب إنشاء إشعار بنجاح.
        """

        notification = self.create_notification()

        self.assertIsNotNone(
            notification.pk
        )

        self.assertFalse(
            notification.is_read
        )

        self.assertIsNone(
            notification.read_at
        )

    def test_default_level_is_info(self):
        """
        المستوى الافتراضي يجب أن يكون معلومات.
        """

        notification = Notification.objects.create(
            user=self.user,
            title="مستوى افتراضي",
            message="اختبار المستوى الافتراضي.",
        )

        self.assertEqual(
            notification.level,
            Notification.Level.INFO,
        )

    def test_notification_levels_are_valid(self):
        """
        يجب دعم جميع مستويات الإشعارات.
        """

        expected_levels = {
            Notification.Level.INFO,
            Notification.Level.SUCCESS,
            Notification.Level.WARNING,
            Notification.Level.DANGER,
        }

        actual_levels = {
            value
            for value, _label
            in Notification.Level.choices
        }

        self.assertEqual(
            actual_levels,
            expected_levels,
        )

    def test_string_representation_contains_title_and_user(self):
        """
        النص الظاهر يجب أن يحتوي العنوان والمستخدم.
        """

        notification = self.create_notification()

        text = str(
            notification
        )

        self.assertIn(
            notification.title,
            text,
        )

        self.assertIn(
            self.user.username,
            text,
        )

    def test_mark_as_read_updates_status_and_time(self):
        """
        تعليم الإشعار كمقروء يحدث الحالة والتاريخ.
        """

        notification = self.create_notification()

        before = timezone.now()

        notification.mark_as_read()

        notification.refresh_from_db()

        after = timezone.now()

        self.assertTrue(
            notification.is_read
        )

        self.assertIsNotNone(
            notification.read_at
        )

        self.assertGreaterEqual(
            notification.read_at,
            before,
        )

        self.assertLessEqual(
            notification.read_at,
            after,
        )

    def test_mark_as_read_is_idempotent(self):
        """
        استدعاء القراءة أكثر من مرة لا يغير تاريخ القراءة.
        """

        notification = self.create_notification()

        notification.mark_as_read()
        notification.refresh_from_db()

        first_read_at = notification.read_at

        notification.mark_as_read()
        notification.refresh_from_db()

        self.assertEqual(
            notification.read_at,
            first_read_at,
        )

    def test_notifications_are_ordered_newest_first(self):
        """
        الترتيب الافتراضي يجب أن يكون من الأحدث إلى الأقدم.
        """

        first = self.create_notification(
            title="الإشعار الأول",
        )

        second = self.create_notification(
            title="الإشعار الثاني",
        )

        notification_ids = list(
            Notification.objects.values_list(
                "id",
                flat=True,
            )
        )

        self.assertEqual(
            notification_ids,
            [
                second.pk,
                first.pk,
            ],
        )

    def test_deleting_user_deletes_notifications(self):
        """
        حذف المستخدم يجب أن يحذف إشعاراته.
        """

        notification = self.create_notification()

        notification_pk = notification.pk

        self.user.delete()

        self.assertFalse(
            Notification.objects.filter(
                pk=notification_pk
            ).exists()
        )