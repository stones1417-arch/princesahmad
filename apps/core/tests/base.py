from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class BasePlatformTestCase(TestCase):
    """
    الفئة الأساسية لاختبارات منصة أبواب.

    توفر:
    - مدير نظام.
    - مستخدم إداري.
    - مستخدم عادي.
    - تسجيل دخول سريع.
    - منح الصلاحيات.
    - أدوات فحص الاستجابات.
    """

    ADMIN_USERNAME = "platform_test_admin"
    ADMIN_PASSWORD = "StrongAdminPassword123!"

    STAFF_USERNAME = "platform_test_staff"
    STAFF_PASSWORD = "StrongStaffPassword123!"

    USER_USERNAME = "platform_test_user"
    USER_PASSWORD = "StrongUserPassword123!"

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        cls.admin_user = User.objects.create_superuser(
            username=cls.ADMIN_USERNAME,
            email="platform-admin@example.com",
            password=cls.ADMIN_PASSWORD,
        )

        cls.staff_user = User.objects.create_user(
            username=cls.STAFF_USERNAME,
            email="platform-staff@example.com",
            password=cls.STAFF_PASSWORD,
            is_staff=True,
            is_active=True,
        )

        cls.normal_user = User.objects.create_user(
            username=cls.USER_USERNAME,
            email="platform-user@example.com",
            password=cls.USER_PASSWORD,
            is_staff=False,
            is_active=True,
        )

        cls.inactive_user = User.objects.create_user(
            username="platform_test_inactive",
            email="platform-inactive@example.com",
            password="StrongInactivePassword123!",
            is_active=False,
        )

    def login_admin(self) -> None:
        """
        تسجيل الدخول بحساب مدير النظام.
        """

        logged_in = self.client.login(
            username=self.ADMIN_USERNAME,
            password=self.ADMIN_PASSWORD,
        )

        self.assertTrue(
            logged_in,
            msg="تعذر تسجيل الدخول بحساب مدير النظام.",
        )

    def login_staff(self) -> None:
        """
        تسجيل الدخول بحساب الموظف الإداري.
        """

        logged_in = self.client.login(
            username=self.STAFF_USERNAME,
            password=self.STAFF_PASSWORD,
        )

        self.assertTrue(
            logged_in,
            msg="تعذر تسجيل الدخول بحساب الموظف الإداري.",
        )

    def login_normal_user(self) -> None:
        """
        تسجيل الدخول بحساب المستخدم العادي.
        """

        logged_in = self.client.login(
            username=self.USER_USERNAME,
            password=self.USER_PASSWORD,
        )

        self.assertTrue(
            logged_in,
            msg="تعذر تسجيل الدخول بحساب المستخدم العادي.",
        )

    def logout(self) -> None:
        """
        إنهاء جلسة المستخدم الحالي.
        """

        self.client.logout()

    @staticmethod
    def grant_permission(
        user,
        *,
        app_label: str,
        codename: str,
    ) -> Permission:
        """
        منح صلاحية محددة لمستخدم.

        مثال:
            self.grant_permission(
                self.staff_user,
                app_label="breaks",
                codename="can_update_employee_break",
            )
        """

        permission = Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

        user.user_permissions.add(permission)

        return permission

    @staticmethod
    def grant_permissions(
        user,
        permissions: list[tuple[str, str]],
    ) -> list[Permission]:
        """
        منح مجموعة صلاحيات للمستخدم.

        permissions:
            [
                ("breaks", "can_view_break_dashboard"),
                ("breaks", "can_update_employee_break"),
            ]
        """

        granted_permissions: list[Permission] = []

        for app_label, codename in permissions:
            permission = Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )

            user.user_permissions.add(permission)
            granted_permissions.append(permission)

        return granted_permissions

    def assert_response_ok(
        self,
        response,
        *,
        expected_status: int = 200,
    ) -> None:
        """
        التحقق من نجاح الاستجابة.
        """

        self.assertEqual(
            response.status_code,
            expected_status,
            msg=(
                f"رمز الاستجابة المتوقع {expected_status}، "
                f"لكن المستلم {response.status_code}."
            ),
        )

    def assert_redirects_to(
        self,
        response,
        url_name: str,
        *,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """
        التحقق من إعادة التوجيه إلى مسار مسمى.
        """

        expected_url = reverse(
            url_name,
            args=args,
            kwargs=kwargs,
        )

        self.assertRedirects(
            response,
            expected_url,
        )

    def assert_message_contains(
        self,
        response,
        expected_text: str,
    ) -> None:
        """
        التحقق من وجود رسالة Django ضمن الاستجابة.
        """

        response_messages = list(
            response.context["messages"]
        )

        message_texts = [
            str(message)
            for message in response_messages
        ]

        self.assertTrue(
            any(
                expected_text in message
                for message in message_texts
            ),
            msg=(
                f"لم يتم العثور على الرسالة: "
                f"{expected_text}\n"
                f"الرسائل الموجودة: {message_texts}"
            ),
        )