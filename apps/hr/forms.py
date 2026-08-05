from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import Employee


class EmployeeForm(forms.ModelForm):

    class Meta:
        model = Employee

        fields = [
            "employee_number",
            "full_name",
            "national_id",
            "phone_number",
            "email",
            "job_title",
            "work_status",
            "can_work_on_doors",
            "can_execute_maintenance",
            "hire_date",
            "notes",
        ]

        widgets = {

            "employee_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "الرقم الوظيفي",
                }
            ),

            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "الاسم الكامل",
                }
            ),

            "national_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "رقم الهوية",
                }
            ),

            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "05xxxxxxxx",
                }
            ),

            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "example@email.com",
                }
            ),

            "job_title": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "work_status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "hire_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "ملاحظات إضافية",
                }
            ),
        }

    def clean_employee_number(self):
        employee_number = (
            self.cleaned_data.get("employee_number") or ""
        ).strip()

        if not employee_number:
            raise ValidationError("الرقم الوظيفي مطلوب")

        return employee_number

    def clean_full_name(self):
        full_name = (
            self.cleaned_data.get("full_name") or ""
        ).strip()

        if not full_name:
            raise ValidationError("الاسم الكامل مطلوب")

        return full_name

    def clean_national_id(self):
        national_id = (
            self.cleaned_data.get("national_id") or ""
        ).strip()

        return national_id

    def clean_phone_number(self):
        phone = (
            self.cleaned_data.get("phone_number") or ""
        ).strip()

        return phone

    def save(self, commit=True):
        employee = super().save(commit=False)

        # تزامن حالة النظام مع حالة الموظف
        employee.is_active = (
            employee.work_status ==
            Employee.WorkStatus.ACTIVE
        )

        if commit:
            employee.save()

        return employee