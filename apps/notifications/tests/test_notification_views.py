from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import Notification


User = get_user_model()


class NotificationViewsTests(TestCase):
    """
    اختبارات واجهات الإشعارات.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="notification_view_user",
            email="notification-view@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

        self.other_user = User.objects.create_user(
            username="notification_other_user",
            email="notification-other@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

        self.notification = Notification.objects.create(
            user=self.user,
            title="إشعار المستخدم",
            message="إشعار خاص بالمستخدم.",
            level=Notification.Level.INFO,
            url="",
        )

        self.other_notification = Notification.objects.create(
            user=self.other_user,
            title="إشعار مستخدم آخر",
            message="يجب ألا يظهر للمستخدم الحالي.",
            level=Notification.Level.WARNING,
            url="",
        )

        self.list_url = reverse(
            "notifications:list"
        )

    def login_user(self):
        logged_in = self.client.login(
            username="notification_view_user",
            password="StrongPassword123!",
        )

        self.assertTrue(
            logged_in
        )

    def test_anonymous_user_is_redirected_from_list(self):
        """
        المستخدم غير المسجل يحول إلى تسجيل الدخول.
        """

        response = self.client.get(
            self.list_url
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertIn(
            "login",
            response.url,
        )

    def test_authenticated_user_can_view_list(self):
        """
        المستخدم المسجل يستطيع عرض قائمة إشعاراته.
        """

        self.login_user()

        response = self.client.get(
            self.list_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "notifications/list.html",
        )

    def test_list_only_contains_current_user_notifications(self):
        """
        يجب ألا تظهر إشعارات المستخدمين الآخرين.
        """

        self.login_user()

        response = self.client.get(
            self.list_url
        )

        notifications = list(
            response.context["notifications"]
        )

        self.assertIn(
            self.notification,
            notifications,
        )

        self.assertNotIn(
            self.other_notification,
            notifications,
        )

    def test_mark_notification_read(self):
        """
        تعليم إشعار المستخدم كمقروء يجب أن ينجح.
        """

        self.login_user()

        read_url = reverse(
            "notifications:read",
            args=[
                self.notification.pk,
            ],
        )

        response = self.client.get(
            read_url
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.notification.refresh_from_db()

        self.assertTrue(
            self.notification.is_read
        )

        self.assertIsNotNone(
            self.notification.read_at
        )

    def test_mark_read_redirects_to_notification_url(self):
        """
        إذا كان للإشعار رابط يجب التحويل إليه.
        """

        self.notification.url = "/ops/doors/"
        self.notification.save(
            update_fields=[
                "url",
            ]
        )

        self.login_user()

        response = self.client.get(
            reverse(
                "notifications:read",
                args=[
                    self.notification.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            "/ops/doors/",
            fetch_redirect_response=False,
        )

    def test_mark_read_without_url_redirects_to_list(self):
        """
        الإشعار دون رابط يعيد المستخدم إلى القائمة.
        """

        self.login_user()

        response = self.client.get(
            reverse(
                "notifications:read",
                args=[
                    self.notification.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

    def test_user_cannot_read_other_user_notification(self):
        """
        لا يمكن للمستخدم قراءة إشعار مستخدم آخر.
        """

        self.login_user()

        response = self.client.get(
            reverse(
                "notifications:read",
                args=[
                    self.other_notification.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.other_notification.refresh_from_db()

        self.assertFalse(
            self.other_notification.is_read
        )

    def test_mark_all_notifications_read(self):
        """
        يجب تعليم جميع إشعارات المستخدم غير المقروءة كمقروءة.
        """

        second_notification = Notification.objects.create(
            user=self.user,
            title="إشعار ثانٍ",
            message="إشعار غير مقروء ثانٍ.",
            level=Notification.Level.SUCCESS,
        )

        self.login_user()

        response = self.client.get(
            reverse(
                "notifications:read-all"
            )
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        self.notification.refresh_from_db()
        second_notification.refresh_from_db()

        self.assertTrue(
            self.notification.is_read
        )

        self.assertTrue(
            second_notification.is_read
        )

    def test_mark_all_does_not_modify_other_user_notifications(self):
        """
        القراءة الجماعية لا تمس إشعارات مستخدم آخر.
        """

        self.login_user()

        self.client.get(
            reverse(
                "notifications:read-all"
            )
        )

        self.other_notification.refresh_from_db()

        self.assertFalse(
            self.other_notification.is_read
        )