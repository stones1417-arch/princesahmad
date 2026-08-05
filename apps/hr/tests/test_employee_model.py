from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.tests.factories import create_employee
from apps.hr.models import Employee


class EmployeeUniqueFieldsTests(TestCase):
    """
    اختبار الحقول الفريدة في نموذج الموظفين.
    """

    def test_duplicate_employee_number_is_rejected(self):
        """
        يجب منع إنشاء موظفين بالرقم الوظيفي نفسه.
        """

        create_employee(
            full_name="الموظف الأول",
            employee_number="64115",
        )

        with self.assertRaises(
            (
                ValidationError,
                IntegrityError,
            )
        ):
            with transaction.atomic():
                duplicate_employee = Employee(
                    full_name="الموظف الثاني",
                    employee_number="64115",
                )

                duplicate_employee.full_clean()
                duplicate_employee.save()

    def test_employee_number_is_saved_correctly(self):
        """
        التأكد من حفظ الرقم الوظيفي بدون تغيير.
        """

        employee = create_employee(
            full_name="أحمد محمد",
            employee_number="123456",
        )

        employee.refresh_from_db()

        self.assertEqual(
            employee.employee_number,
            "123456",
        )

    def test_employee_full_name_is_required(self):
        """
        يجب منع إنشاء موظف دون اسم.
        """

        employee = Employee(
            full_name="",
            employee_number="70001",
        )

        with self.assertRaises(ValidationError):
            employee.full_clean()


class EmployeeNationalIdTests(TestCase):
    """
    اختبار رقم الهوية.

    تعمل الاختبارات إذا كان نموذج Employee يحتوي
    على حقل national_id.
    """

    def setUp(self):
        self.employee_fields = {
            field.name
            for field in Employee._meta.fields
        }

    def test_duplicate_national_id_is_rejected(self):
        """
        يجب منع رقم الهوية المكرر.
        """

        if "national_id" not in self.employee_fields:
            self.skipTest(
                "نموذج Employee لا يحتوي على حقل national_id."
            )

        create_employee(
            full_name="موظف الهوية الأول",
            employee_number="71001",
            national_id="1012345678",
        )

        with self.assertRaises(
            (
                ValidationError,
                IntegrityError,
            )
        ):
            with transaction.atomic():
                create_employee(
                    full_name="موظف الهوية الثاني",
                    employee_number="71002",
                    national_id="1012345678",
                )

    def test_valid_national_id_is_saved(self):
        """
        التأكد من حفظ رقم الهوية الصحيح.
        """

        if "national_id" not in self.employee_fields:
            self.skipTest(
                "نموذج Employee لا يحتوي على حقل national_id."
            )

        employee = create_employee(
            full_name="موظف اختبار الهوية",
            employee_number="71003",
            national_id="1098765432",
        )

        employee.refresh_from_db()

        self.assertEqual(
            employee.national_id,
            "1098765432",
        )

    def test_short_national_id_is_rejected(self):
        """
        يجب رفض رقم الهوية الناقص إذا كانت قاعدة التحقق مطبقة.
        """

        if "national_id" not in self.employee_fields:
            self.skipTest(
                "نموذج Employee لا يحتوي على حقل national_id."
            )

        employee = create_employee(
            full_name="موظف رقم قصير",
            employee_number="71004",
        )

        employee.national_id = "1234"

        with self.assertRaises(ValidationError):
            employee.full_clean()