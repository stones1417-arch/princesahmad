from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import create_employee, create_user
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole


class EmployeeListViewTests(TestCase):
    def setUp(self):
        self.url = reverse("hr:list")

        self.male_employee = create_employee(
            full_name="موظف رجالي",
            employee_number="92001",
            operational_section=Employee.OperationalSection.MALE,
            job_title=Employee.JobTitle.MONITOR,
            work_status=Employee.WorkStatus.ACTIVE,
            is_active=True,
        )
        self.female_employee = create_employee(
            full_name="موظفة نسائية",
            employee_number="92002",
            operational_section=Employee.OperationalSection.FEMALE,
            job_title=Employee.JobTitle.TECHNICIAN,
            work_status=Employee.WorkStatus.ACTIVE,
            is_active=True,
        )

    def _login_staff_with_permissions(self, *codenames: str):
        user = create_user(
            username="hr_staff_user",
        )
        view_male = "can_view_male_employees" in codenames
        view_female = "can_view_female_employees" in codenames

        if view_male or view_female:
            scope = (
                Role.OperationalSection.ALL
                if view_male and view_female
                else (
                    Role.OperationalSection.MALE
                    if view_male
                    else Role.OperationalSection.FEMALE
                )
            )
            group = Group.objects.create(name="hr list group")
            group.permissions.add(
                Permission.objects.get(
                    content_type__app_label="roles",
                    codename="view_employees",
                )
            )
            role = Role.objects.create(
                code="hr-list-role",
                name="hr list role",
                group=group,
                operational_section=scope,
            )
            UserRole.objects.create(user=user, role=role)
        self.client.force_login(user)
        return user

    def test_shows_only_male_employees_when_user_has_male_permission_only(self):
        self._login_staff_with_permissions(
            "can_view_male_employees",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.male_employee.full_name)
        self.assertNotContains(response, self.female_employee.full_name)

        self.assertEqual(response.context["total_employees"], 1)
        self.assertEqual(response.context["male_employees"], 1)
        self.assertEqual(response.context["female_employees"], 0)
        self.assertTrue(response.context["can_view_male"])
        self.assertFalse(response.context["can_view_female"])
        self.assertEqual(
            list(response.context["employee_operational_section_choices"]),
            [
                (
                    Employee.OperationalSection.MALE,
                    "رجالي",
                )
            ],
        )
        self.assertContains(
            response,
            "يتم عرض موظفي القسم الرجالي فقط حسب الصلاحيات الحالية.",
        )

    def test_shows_only_female_employees_when_user_has_female_permission_only(self):
        self._login_staff_with_permissions(
            "can_view_female_employees",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.female_employee.full_name)
        self.assertNotContains(response, self.male_employee.full_name)

        self.assertEqual(response.context["total_employees"], 1)
        self.assertEqual(response.context["male_employees"], 0)
        self.assertEqual(response.context["female_employees"], 1)
        self.assertFalse(response.context["can_view_male"])
        self.assertTrue(response.context["can_view_female"])
        self.assertEqual(
            list(response.context["employee_operational_section_choices"]),
            [
                (
                    Employee.OperationalSection.FEMALE,
                    "نسائي",
                )
            ],
        )

    def test_institutional_role_scope_limits_employee_results(self):
        user = create_user(
            username="male_role_supervisor",
            is_staff=True,
        )
        role = Role.objects.create(
            code="male-role-supervisor",
            name="male-role-supervisor",
            group=Group.objects.create(
                name="male-role-supervisor",
            ),
            operational_section=Role.OperationalSection.MALE,
        )
        role.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="view_employees",
            )
        )
        UserRole.objects.create(user=user, role=role)
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(
                response.context["employees"].values_list(
                    "id",
                    flat=True,
                )
            ),
            [self.male_employee.id],
        )
        self.assertTrue(response.context["can_view_male"])
        self.assertFalse(response.context["can_view_female"])

        forbidden_response = self.client.get(
            self.url,
            {"operational_section": Employee.OperationalSection.FEMALE},
        )
        self.assertEqual(
            forbidden_response.context["employees"].count(),
            0,
        )

    def test_denies_user_without_platform_view_permission(self):
        self._login_staff_with_permissions()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_applies_operational_section_filter_and_persists_selected_value(self):
        self._login_staff_with_permissions(
            "can_view_male_employees",
            "can_view_female_employees",
        )

        response = self.client.get(
            self.url,
            {
                "operational_section": Employee.OperationalSection.FEMALE,
                "sort": "full_name",
                "direction": "desc",
                "q": "نسائية",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.female_employee.full_name)
        self.assertNotContains(response, self.male_employee.full_name)

        self.assertEqual(
            response.context["selected_operational_section"],
            Employee.OperationalSection.FEMALE,
        )
        self.assertEqual(response.context["selected_sort"], "full_name")
        self.assertEqual(response.context["selected_direction"], "desc")
        self.assertEqual(response.context["q"], "نسائية")

    def test_ignores_invalid_operational_section_filter_value(self):
        self._login_staff_with_permissions(
            "can_view_male_employees",
            "can_view_female_employees",
        )

        response = self.client.get(
            self.url,
            {
                "operational_section": "invalid-section",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.male_employee.full_name)
        self.assertContains(response, self.female_employee.full_name)
        self.assertEqual(response.context["employees"].count(), 2)

    def test_shows_clear_empty_results_message_when_filters_match_nothing(self):
        self._login_staff_with_permissions(
            "can_view_male_employees",
            "can_view_female_employees",
        )

        response = self.client.get(
            self.url,
            {
                "q": "بحث-لا-يطابق-أي-موظف",
                "operational_section": Employee.OperationalSection.MALE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["employees"].count(), 0)
        self.assertContains(response, "لا توجد نتائج مطابقة")
        self.assertContains(
            response,
            "جرّب تعديل الفلاتر أو إعادة ضبطها.",
        )

    def test_two_factor_readiness_filter_returns_only_matching_employees(self):
        ready_user = create_user(username="ready-employee", email="ready@example.test")
        self.male_employee.user = ready_user
        self.male_employee.email = "ready@example.test"
        self.male_employee.phone_number = ""
        self.male_employee.save()
        self.female_employee.phone_number = "0501234567"
        self.female_employee.email = ""
        self.female_employee.save()
        self._login_staff_with_permissions(
            "can_view_male_employees",
            "can_view_female_employees",
        )

        response = self.client.get(self.url, {"two_factor_readiness": "not-ready"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["employees"]), [self.female_employee])
        self.assertContains(response, "NOT READY")
        self.assertNotContains(response, "0501234567")

        response = self.client.get(self.url, {"two_factor_readiness": "ready"})

        self.assertEqual(list(response.context["employees"]), [self.male_employee])
        self.assertContains(response, "READY")
        self.assertNotContains(response, "ready@example.test")
