from __future__ import annotations

from django.test import TestCase

from apps.communications.services.otp_validation import normalize_saudi_phone_number
from apps.hr.forms import EmployeeForm
from apps.hr.models import Employee


class EmployeeFormTests(TestCase):
    def test_operational_section_field_includes_placeholder_and_choices(self):
        form = EmployeeForm()

        self.assertIn("operational_section", form.fields)
        self.assertEqual(
            form.fields["operational_section"].choices[0],
            ("", "اختر القسم التشغيلي"),
        )
        self.assertIn(
            (Employee.OperationalSection.MALE, "رجالي"),
            form.fields["operational_section"].choices,
        )
        self.assertIn(
            (Employee.OperationalSection.FEMALE, "نسائي"),
            form.fields["operational_section"].choices,
        )

    def test_form_rejects_missing_operational_section(self):
        form = EmployeeForm(
            data={
                "employee_number": "81000",
                "full_name": "موظف اختبار",
                "operational_section": "",
                "job_title": Employee.JobTitle.MONITOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("operational_section", form.errors)
        self.assertIn(
            "يجب اختيار القسم التشغيلي",
            form.errors["operational_section"][0],
        )

    def test_form_rejects_invalid_operational_section_value(self):
        form = EmployeeForm(
            data={
                "employee_number": "81001",
                "full_name": "موظف خاطئ",
                "operational_section": "unknown",
                "job_title": Employee.JobTitle.MONITOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("operational_section", form.errors)
        self.assertIn(
            "رجالي أو نسائي",
            form.errors["operational_section"][0],
        )

    def test_form_accepts_valid_operational_section(self):
        form = EmployeeForm(
            data={
                "employee_number": "81002",
                "full_name": "موظف صالح",
                "operational_section": Employee.OperationalSection.MALE,
                "job_title": Employee.JobTitle.MONITOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertTrue(form.is_valid())
        employee = form.save(commit=False)
        self.assertEqual(
            employee.operational_section,
            Employee.OperationalSection.MALE,
        )

    def test_form_accepts_female_operational_section(self):
        form = EmployeeForm(
            data={
                "employee_number": "81003",
                "full_name": "موظفة صالحة",
                "operational_section": Employee.OperationalSection.FEMALE,
                "job_title": Employee.JobTitle.MONITOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertTrue(form.is_valid())
        employee = form.save(commit=False)
        self.assertEqual(
            employee.operational_section,
            Employee.OperationalSection.FEMALE,
        )

    def test_female_section_uses_feminine_job_title_labels(self):
        form = EmployeeForm(
            data={
                "employee_number": "81004",
                "full_name": "موظفة مسميات",
                "operational_section": Employee.OperationalSection.FEMALE,
                "job_title": Employee.JobTitle.FAJR_SUPERVISOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertEqual(
            dict(form.fields["job_title"].choices)[
                Employee.JobTitle.FAJR_SUPERVISOR
            ],
            "مشرفة وردية الفجر",
        )
        self.assertEqual(
            form.job_title_labels["female"][
                Employee.JobTitle.DOORS_HEAD
            ],
            "رئيسة قسم الأبواب",
        )
        self.assertEqual(
            form.job_title_labels["male"][
                Employee.JobTitle.DOORS_HEAD
            ],
            "رئيس قسم الأبواب",
        )

    def test_phone_normalizer_accepts_saudi_mobile_variants(self):
        for raw, expected in [
            ("0501234567", "+966501234567"),
            ("501234567", "+966501234567"),
            ("966501234567", "+966501234567"),
            ("+966501234567", "+966501234567"),
            ("050 123 4567", "+966501234567"),
            ("050-123-4567", "+966501234567"),
        ]:
            self.assertEqual(normalize_saudi_phone_number(raw), expected)

    def test_form_normalizes_valid_saudi_mobile_variants(self):
        for raw in [
            "0501234567",
            "501234567",
            "966501234567",
            "+966501234567",
            "050 123 4567",
            "050-123-4567",
        ]:
            form = EmployeeForm(
                data={
                    "employee_number": "81005",
                    "full_name": "موظف جوال",
                    "operational_section": Employee.OperationalSection.MALE,
                    "phone_number": raw,
                    "job_title": Employee.JobTitle.MONITOR,
                    "work_status": Employee.WorkStatus.ACTIVE,
                }
            )

            self.assertTrue(form.is_valid(), msg=f"raw={raw!r} errors={form.errors}")
            self.assertEqual(form.cleaned_data["phone_number"], "+966501234567")

    def test_form_rejects_invalid_mobile_numbers(self):
        for raw in [
            "123",
            "+9664",
            "abc",
            "050123456",
            "05012345678",
            "96650123456",
            "+96650123456",
        ]:
            form = EmployeeForm(
                data={
                    "employee_number": "81006",
                    "full_name": "موظف جوال خاطئ",
                    "operational_section": Employee.OperationalSection.MALE,
                    "phone_number": raw,
                    "job_title": Employee.JobTitle.MONITOR,
                    "work_status": Employee.WorkStatus.ACTIVE,
                }
            )

            self.assertFalse(form.is_valid(), msg=f"raw={raw!r} should be invalid")
            self.assertIn("phone_number", form.errors)
            self.assertIn("أدخل رقم جوال سعودي صحيحًا", form.errors["phone_number"][0])

    def test_form_rejects_invalid_email(self):
        form = EmployeeForm(
            data={
                "employee_number": "81007",
                "full_name": "موظف بريد خاطئ",
                "operational_section": Employee.OperationalSection.MALE,
                "email": "not-an-email",
                "job_title": Employee.JobTitle.MONITOR,
                "work_status": Employee.WorkStatus.ACTIVE,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
