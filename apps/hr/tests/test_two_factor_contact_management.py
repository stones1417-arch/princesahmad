from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import TwoFactorAuditLog
from apps.accounts.services.two_factor_readiness import get_employee_2fa_readiness_details
from apps.core.tests.factories import create_employee, create_user
from apps.hr.models import Employee
from apps.roles.models import Role, UserRole


@override_settings(AUTHENTICA_OTP_ALLOWED_CHANNELS=("sms", "whatsapp", "email"))
class TwoFactorContactManagementTests(TestCase):
    def setUp(self):
        self.staff_user = create_user(username="contact-admin", is_staff=True)
        group = Group.objects.create(name="contact manager group")
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="update_employee",
            ),
            Permission.objects.get(
                content_type__app_label="roles",
                codename="view_employees",
            ),
        )
        role = Role.objects.create(
            code="contact-manager",
            name="contact manager",
            group=group,
            operational_section=Role.OperationalSection.MALE,
        )
        UserRole.objects.create(user=self.staff_user, role=role)
        self.employee_user = create_user(username="contact-employee", email="")
        self.employee_user.email = ""
        self.employee_user.save(update_fields=["email"])
        self.employee = create_employee(
            user=self.employee_user,
            phone_number="",
            email="",
            operational_section=Employee.OperationalSection.MALE,
        )

    def test_employee_without_contact_data_is_not_ready(self):
        details = get_employee_2fa_readiness_details(self.employee)

        self.assertEqual(details["channels"], [])
        self.assertEqual(details["reason"], "No OTP contact details")

    def test_employee_without_user_is_not_ready(self):
        employee = create_employee(user=None, phone_number="", email="")

        details = get_employee_2fa_readiness_details(employee)

        self.assertEqual(details["channels"], [])
        self.assertEqual(details["reason"], "No linked user account")

    def test_email_only_employee_is_ready(self):
        self.employee.email = "employee@example.test"
        self.employee.save()

        self.assertEqual(get_employee_2fa_readiness_details(self.employee)["channels"], ["email"])

    def test_mobile_employee_has_sms_and_whatsapp_channels(self):
        self.employee.phone_number = "+966501234567"
        self.employee.save()

        self.assertEqual(
            get_employee_2fa_readiness_details(self.employee)["channels"],
            ["sms", "whatsapp"],
        )

    @override_settings(AUTHENTICA_OTP_ALLOWED_CHANNELS=("whatsapp",))
    def test_whatsapp_only_configuration_is_reported(self):
        self.employee.phone_number = "+966501234567"
        self.employee.save()

        self.assertEqual(get_employee_2fa_readiness_details(self.employee)["channels"], ["whatsapp"])

    def test_non_staff_cannot_open_contact_edit_page(self):
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("hr:update", args=[self.employee.pk]))

        self.assertEqual(response.status_code, 403)

    def test_staff_edit_page_shows_masked_two_factor_details(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("hr:update", args=[self.employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بيانات التحقق الثنائي")
        self.assertContains(response, "NOT READY")

    def test_contact_update_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff_user)

        response = csrf_client.post(reverse("hr:update", args=[self.employee.pk]), {})

        self.assertEqual(response.status_code, 403)

    def _post_employee_update(self, *, email=None, phone_number=None, notes=None):
        return self.client.post(
            reverse("hr:update", args=[self.employee.pk]),
            {
                "user": self.employee_user.pk,
                "employee_number": self.employee.employee_number,
                "full_name": self.employee.full_name,
                "operational_section": self.employee.operational_section,
                "national_id": self.employee.national_id,
                "phone_number": self.employee.phone_number if phone_number is None else phone_number,
                "email": self.employee.email if email is None else email,
                "job_title": self.employee.job_title,
                "work_status": self.employee.work_status,
                "is_active": "on",
                "can_work_on_doors": "on",
                "hire_date": self.employee.hire_date.isoformat() if self.employee.hire_date else "",
                "notes": self.employee.notes if notes is None else notes,
            },
        )

    def test_email_only_change_records_only_email_field(self):
        self.client.force_login(self.staff_user)

        response = self._post_employee_update(email="updated@example.test")

        self.assertRedirects(response, reverse("hr:list"))
        event = TwoFactorAuditLog.objects.get(user=self.employee_user, event="2fa_contact_updated")
        self.assertEqual(event.metadata["changed_fields"], "email")
        self.assertEqual(event.metadata["employee_id"], self.employee.pk)

    def test_mobile_only_change_records_only_phone_field(self):
        self.client.force_login(self.staff_user)

        response = self._post_employee_update(phone_number="+966509876543")

        self.assertRedirects(response, reverse("hr:list"))
        event = TwoFactorAuditLog.objects.get(user=self.employee_user, event="2fa_contact_updated")
        self.assertEqual(event.metadata["changed_fields"], "phone_number")

    def test_non_contact_update_does_not_create_two_factor_audit_event(self):
        self.client.force_login(self.staff_user)

        response = self._post_employee_update(notes="Administrative note")

        self.assertRedirects(response, reverse("hr:list"))
        self.assertFalse(
            TwoFactorAuditLog.objects.filter(
                user=self.employee_user,
                event="2fa_contact_updated",
            ).exists()
        )

    def test_staff_contact_change_records_sanitized_audit_event(self):
        self.client.force_login(self.staff_user)
        new_email = "updated@example.test"
        new_phone = "+966509876543"

        response = self._post_employee_update(email=new_email, phone_number=new_phone)

        self.assertRedirects(response, reverse("hr:list"))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.email, new_email)
        self.assertEqual(self.employee.phone_number, new_phone)
        audit_event = TwoFactorAuditLog.objects.get(
            user=self.employee_user,
            event="2fa_contact_updated",
        )
        self.assertEqual(audit_event.metadata["actor_id"], self.staff_user.pk)
        self.assertEqual(audit_event.metadata["employee_id"], self.employee.pk)
        self.assertEqual(audit_event.metadata["changed_fields"], "email,phone_number")
        self.assertNotIn(new_email, str(audit_event.metadata))
        self.assertNotIn(new_phone, str(audit_event.metadata))