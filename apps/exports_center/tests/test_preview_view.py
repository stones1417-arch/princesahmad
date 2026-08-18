from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_door, create_employee
from apps.roles.models import Role, UserRole


class PreviewViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="preview_user",
            password="StrongPassword123!",
        )
        group = Group.objects.create(name="preview-exporters")
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="export_report",
            )
        )
        role = Role.objects.create(
            code="preview-exporter",
            name="Preview exporter",
            group=group,
            operational_section=Role.OperationalSection.ALL,
        )
        UserRole.objects.create(user=self.user, role=role)
        self.client.force_login(self.user)

    def test_preview_view_displays_operational_section_filter_label(self):
        create_door(
            door_number=17,
            is_active=True,
            operational_section="shared",
        )

        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "locations"},
            ),
            {
                "operational_section": "shared",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "القسم التشغيلي")
        self.assertContains(response, "مشترك")

    def test_preview_view_marks_selected_available_columns(self):
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            [("selected_columns", "full_name")],
        )

        self.assertEqual(response.status_code, 200)
        available_columns = response.context["available_columns"]
        selected_columns = [
            column["key"]
            for column in available_columns
            if column["selected"]
        ]

        self.assertEqual(selected_columns, ["full_name"])

    def test_preview_view_renders_section_and_column_controls(self):
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            {
                "section": "female",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "القسم التشغيلي:")
        self.assertContains(response, "تحديد الكل")
        self.assertContains(response, "إلغاء الكل")
        self.assertContains(response, "data-column-checkbox")
        self.assertContains(
            response,
            "data-export-selection-status",
        )

    def test_preview_view_uses_post_forms_for_export_actions(self):
        create_employee(
            full_name="Export Form Employee",
            employee_number="preview-export-form",
            operational_section="female",
        )
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            {
                "operational_section": "female",
                "selected_columns": ["full_name"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="xep-export-form"', count=3)
        self.assertContains(response, 'name="report_key"')
        self.assertContains(response, 'name="export_format"')
        self.assertContains(response, 'name="selected_columns"')

    def test_employee_preview_filters_q_and_section(self):
        create_employee(
            full_name="Needle Male",
            employee_number="preview-male",
            operational_section="male",
        )
        create_employee(
            full_name="Other Female",
            employee_number="preview-female",
            operational_section="female",
        )

        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            {"q": "Needle", "operational_section": "male"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["records_count"], 1)
        self.assertEqual(response.context["records"][0].full_name, "Needle Male")

    def test_employee_preview_empty_result_is_200(self):
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            {"q": "does-not-exist"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["records_count"], 0)

    def test_invalid_section_redirects_instead_of_500(self):
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            ),
            {"operational_section": "invalid"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "exports_center:filters",
                kwargs={"report_key": "employees"},
            ),
        )

    def test_preview_requires_login(self):
        self.client.logout()
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_preview_rejects_authenticated_user_without_export_permission(self):
        unauthorized = get_user_model().objects.create_user(
            username="preview-unauthorized"
        )
        self.client.force_login(unauthorized)
        response = self.client.get(
            reverse(
                "exports_center:preview",
                kwargs={"report_key": "employees"},
            )
        )

        self.assertEqual(response.status_code, 403)
