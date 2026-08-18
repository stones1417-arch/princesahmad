from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.roles.models import Role, UserRole


class FiltersViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="filters_user",
            password="StrongPassword123!",
        )
        group = Group.objects.create(name="filter-exporters")
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="export_report",
            )
        )
        role = Role.objects.create(
            code="filter-exporter",
            name="Filter exporter",
            group=group,
            operational_section=Role.OperationalSection.ALL,
        )
        UserRole.objects.create(user=self.user, role=role)
        self.client.force_login(self.user)

    def test_filters_view_renders_with_form(self):
        response = self.client.get(
            reverse("exports_center:filters", kwargs={"report_key": "employees"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("filter_form", response.context)
        form = response.context["filter_form"]
        self.assertTrue(hasattr(form, "fields"))
        self.assertIn("q", form.fields)
        self.assertIn("operational_section", form.fields)
        self.assertEqual(
            form.fields["operational_section"].choices[0],
            ("", "الكل"),
        )

    def test_filters_view_includes_section_field_for_distribution_report(self):
        response = self.client.get(
            reverse("exports_center:filters", kwargs={"report_key": "door_distribution"})
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["filter_form"]
        self.assertIn("section", form.fields)
        self.assertEqual(
            form.fields["section"].choices[0],
            ("", "الكل"),
        )

    def test_filters_view_includes_operational_section_for_locations_report(self):
        response = self.client.get(
            reverse("exports_center:filters", kwargs={"report_key": "locations"})
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["filter_form"]
        self.assertIn("operational_section", form.fields)
        self.assertEqual(
            form.fields["operational_section"].choices[0],
            ("", "الكل"),
        )

        self.assertIn(
            ("shared", "مشترك"),
            form.fields["operational_section"].choices,
        )
