from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.notifications.context_processors import (
    notifications_badge,
)
from apps.notifications.models import Notification


User = get_user_model()


class NotificationsContextProcessorTests(TestCase):
    """
    اختبارات معالج سياق عداد الإشعارات.
    """

    def setUp(self):
        self.factory = RequestFactory()

        self.user = User.objects.create_user(
            username="notification_context_user",
            password="StrongPassword123!",
            is_active=True,
        )

    def test_anonymous_user_gets_zero_badge(self):
        """
        المستخدم غير المسجل يجب أن يحصل على عداد صفر.
        """

        request = self.factory.get(
            "/"
        )

        request.user = SimpleNamespace(
            is_authenticated=False,
        )

        context = notifications_badge(
            request
        )

        badge_values = list(
            context.values()
        )

        self.assertIn(
            0,
            badge_values,
        )

    def test_unread_count_matches_current_user(self):
        """
        عداد الإشعارات يجب أن يطابق غير المقروء للمستخدم.
        """

        Notification.objects.create(
            user=self.user,
            title="غير مقروء 1",
            message="اختبار",
            is_read=False,
        )

        Notification.objects.create(
            user=self.user,
            title="غير مقروء 2",
            message="اختبار",
            is_read=False,
        )

        Notification.objects.create(
            user=self.user,
            title="مقروء",
            message="اختبار",
            is_read=True,
        )

        request = self.factory.get(
            "/"
        )
        request.user = self.user

        context = notifications_badge(
            request
        )

        self.assertIn(
            2,
            context.values(),
        )