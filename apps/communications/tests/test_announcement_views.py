from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.communications.models import Announcement
from apps.dashboard.models import SystemActivityLog


User = get_user_model()


class AnnouncementViewsTests(TestCase):
    """
    اختبارات واجهات التعاميم الإدارية.
    """

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="announcement_staff",
            email="announcement-staff@example.com",
            password="StrongPassword123!",
            is_staff=True,
            is_active=True,
        )

        self.normal_user = User.objects.create_user(
            username="announcement_normal",
            email="announcement-normal@example.com",
            password="StrongPassword123!",
            is_staff=False,
            is_active=True,
        )

        self.active_announcement = (
            Announcement.objects.create(
                title="تعميم نشط",
                content="محتوى تعميم نشط.",
                priority=Announcement.Priority.NORMAL,
                is_active=True,
                created_by=self.staff_user,
            )
        )

        self.urgent_announcement = (
            Announcement.objects.create(
                title="تعميم عاجل",
                content="محتوى تعميم عاجل.",
                priority=Announcement.Priority.URGENT,
                is_active=True,
                created_by=self.staff_user,
            )
        )

        self.inactive_announcement = (
            Announcement.objects.create(
                title="تعميم غير نشط",
                content="محتوى تعميم غير نشط.",
                priority=Announcement.Priority.IMPORTANT,
                is_active=False,
                created_by=self.staff_user,
            )
        )

        self.list_url = reverse(
            "communications:list"
        )

    def login_staff(self):
        logged_in = self.client.login(
            username="announcement_staff",
            password="StrongPassword123!",
        )

        self.assertTrue(
            logged_in
        )

    def test_anonymous_user_is_redirected(self):
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

    def test_normal_user_cannot_access_list(self):
        """
        المستخدم غير الإداري لا يصل إلى قائمة التعاميم.
        """

        self.client.login(
            username="announcement_normal",
            password="StrongPassword123!",
        )

        response = self.client.get(
            self.list_url
        )

        self.assertIn(
            response.status_code,
            (
                302,
                403,
            ),
        )

    def test_staff_user_can_access_list(self):
        """
        الموظف الإداري يستطيع عرض القائمة.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "communications/announcement_list.html",
        )

    def test_list_context_statistics_are_correct(self):
        """
        يجب أن تكون إحصائيات التعاميم صحيحة.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url
        )

        self.assertEqual(
            response.context["total_announcements"],
            3,
        )

        self.assertEqual(
            response.context["active_announcements"],
            2,
        )

        self.assertEqual(
            response.context["inactive_announcements"],
            1,
        )

        self.assertEqual(
            response.context["urgent_announcements"],
            1,
        )

    def test_search_filter_by_title(self):
        """
        البحث بالعنوان يجب أن يطبق.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url,
            {
                "q": "عاجل",
            },
        )

        announcements = list(
            response.context["announcements"]
        )

        self.assertEqual(
            announcements,
            [
                self.urgent_announcement,
            ],
        )

    def test_search_filter_by_content(self):
        """
        البحث في المحتوى يجب أن يطبق.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url,
            {
                "q": "غير نشط",
            },
        )

        announcements = list(
            response.context["announcements"]
        )

        self.assertIn(
            self.inactive_announcement,
            announcements,
        )

    def test_priority_filter(self):
        """
        فلتر الأولوية يجب أن يطبق.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url,
            {
                "priority": (
                    Announcement.Priority.URGENT
                ),
            },
        )

        announcements = list(
            response.context["announcements"]
        )

        self.assertEqual(
            announcements,
            [
                self.urgent_announcement,
            ],
        )

    def test_active_status_filter(self):
        """
        فلتر التعاميم النشطة يجب أن يطبق.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url,
            {
                "status": "active",
            },
        )

        announcements = list(
            response.context["announcements"]
        )

        self.assertIn(
            self.active_announcement,
            announcements,
        )

        self.assertIn(
            self.urgent_announcement,
            announcements,
        )

        self.assertNotIn(
            self.inactive_announcement,
            announcements,
        )

    def test_inactive_status_filter(self):
        """
        فلتر التعاميم غير النشطة يجب أن يطبق.
        """

        self.login_staff()

        response = self.client.get(
            self.list_url,
            {
                "status": "inactive",
            },
        )

        announcements = list(
            response.context["announcements"]
        )

        self.assertEqual(
            announcements,
            [
                self.inactive_announcement,
            ],
        )

    def test_staff_can_view_announcement_detail(self):
        """
        الإداري يستطيع عرض تفاصيل التعميم.
        """

        self.login_staff()

        response = self.client.get(
            reverse(
                "communications:detail",
                args=[
                    self.active_announcement.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context["announcement"],
            self.active_announcement,
        )

        self.assertTemplateUsed(
            response,
            "communications/announcement_detail.html",
        )

    @patch(
        "apps.communications.views."
        "NotificationService.success"
    )
    def test_staff_can_create_announcement(
        self,
        notification_mock,
    ):
        """
        الإداري يستطيع إنشاء تعميم.
        """

        self.login_staff()

        response = self.client.post(
            reverse(
                "communications:create"
            ),
            {
                "title": "تعميم جديد",
                "content": "محتوى التعميم الجديد.",
                "priority": (
                    Announcement.Priority.IMPORTANT
                ),
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        announcement = Announcement.objects.get(
            title="تعميم جديد"
        )

        self.assertEqual(
            announcement.created_by_id,
            self.staff_user.pk,
        )

        self.assertEqual(
            announcement.priority,
            Announcement.Priority.IMPORTANT,
        )

        notification_mock.assert_called_once()

    @patch(
        "apps.communications.views."
        "NotificationService.info"
    )
    def test_staff_can_update_announcement(
        self,
        notification_mock,
    ):
        """
        الإداري يستطيع تعديل التعميم.
        """

        self.login_staff()

        response = self.client.post(
            reverse(
                "communications:edit",
                args=[
                    self.active_announcement.pk,
                ],
            ),
            {
                "title": "تعميم معدل",
                "content": "تم تعديل محتوى التعميم.",
                "priority": (
                    Announcement.Priority.URGENT
                ),
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        self.active_announcement.refresh_from_db()

        self.assertEqual(
            self.active_announcement.title,
            "تعميم معدل",
        )

        self.assertEqual(
            self.active_announcement.priority,
            Announcement.Priority.URGENT,
        )

        notification_mock.assert_called_once()

    def test_toggle_status_requires_post(self):
        """
        GET لا يجب أن يغير حالة التعميم.
        """

        self.login_staff()

        response = self.client.get(
            reverse(
                "communications:toggle-status",
                args=[
                    self.active_announcement.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        self.active_announcement.refresh_from_db()

        self.assertTrue(
            self.active_announcement.is_active
        )

    @patch(
        "apps.communications.views."
        "NotificationService.warning"
    )
    def test_staff_can_toggle_status(
        self,
        notification_mock,
    ):
        """
        الإداري يستطيع تعطيل التعميم وتفعيله.
        """

        self.login_staff()

        response = self.client.post(
            reverse(
                "communications:toggle-status",
                args=[
                    self.active_announcement.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        self.active_announcement.refresh_from_db()

        self.assertFalse(
            self.active_announcement.is_active
        )

        notification_mock.assert_called_once()

    def test_delete_get_displays_confirmation_page(self):
        """
        GET للحذف يجب أن يعرض صفحة التأكيد.
        """

        self.login_staff()

        response = self.client.get(
            reverse(
                "communications:delete",
                args=[
                    self.active_announcement.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            (
                "communications/"
                "announcement_confirm_delete.html"
            ),
        )

    @patch(
        "apps.communications.views."
        "NotificationService.danger"
    )
    def test_staff_can_delete_announcement(
        self,
        notification_mock,
    ):
        """
        الإداري يستطيع حذف تعميم.
        """

        self.login_staff()

        announcement_pk = (
            self.active_announcement.pk
        )

        response = self.client.post(
            reverse(
                "communications:delete",
                args=[
                    announcement_pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )

        self.assertFalse(
            Announcement.objects.filter(
                pk=announcement_pk
            ).exists()
        )

        notification_mock.assert_called_once()

    def test_create_registers_system_activity(self):
        """
        إنشاء التعميم يجب أن يسجل نشاطًا نظاميًا.
        """

        self.login_staff()

        previous_count = (
            SystemActivityLog.objects.count()
        )

        self.client.post(
            reverse(
                "communications:create"
            ),
            {
                "title": "تعميم سجل النشاط",
                "content": "تعميم لاختبار سجل النشاط.",
                "priority": (
                    Announcement.Priority.NORMAL
                ),
                "is_active": "on",
            },
        )

        self.assertEqual(
            SystemActivityLog.objects.count(),
            previous_count + 1,
        )

        activity = (
            SystemActivityLog.objects
            .latest("id")
        )

        self.assertEqual(
            activity.module,
            "التعاميم الإدارية",
        )

        self.assertEqual(
            activity.action,
            SystemActivityLog.ActionType.CREATE,
        )