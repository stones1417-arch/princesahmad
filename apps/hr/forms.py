from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import Employee


class EmployeeForm(forms.ModelForm):

    FEMALE_JOB_TITLE_LABELS = {
        Employee.JobTitle.CHAIRMAN_OFFICE: "مكتب معالي: رئيسة مجلس الإدارة",
        Employee.JobTitle.CEO_OFFICE: "مكتب الرئيسة التنفيذية",
        Employee.JobTitle.DEPUTY_CEO_OPERATIONS: "نائبة الرئيسة التنفيذية للتشغيل للمسجد النبوي الشريف",
        Employee.JobTitle.GM: "المديرة العامة",
        Employee.JobTitle.DOORS_HEAD: "رئيسة قسم الأبواب",
        Employee.JobTitle.DOORS_DEPUTY: "وكيلة رئيسة قسم الأبواب",
        Employee.JobTitle.SENIOR_ADMIN: "كبيرة الإداريات للأبواب",
        Employee.JobTitle.ADMIN_SECRETARY: "سكرتيرة إدارية",
        Employee.JobTitle.FAJR_SUPERVISOR: "مشرفة وردية الفجر",
        Employee.JobTitle.DUHA_SUPERVISOR: "مشرفة وردية الضحى",
        Employee.JobTitle.EVENING_SUPERVISOR: "مشرفة وردية مسائية",
        Employee.JobTitle.SUPPORT_SUPERVISOR: "مشرفة وردية مساندة",
        Employee.JobTitle.FAJR_DEPUTY: "نائبة مشرفة الفجر",
        Employee.JobTitle.DUHA_DEPUTY: "نائبة مشرفة الضحى",
        Employee.JobTitle.EVENING_DEPUTY: "نائبة مشرفة المسائية",
        Employee.JobTitle.TECH_SECRETARY: "سكرتيرة فنية",
        Employee.JobTitle.TECHNICIAN: "فنية صيانة",
        Employee.JobTitle.MONITOR: "مراقبة أبواب",
        Employee.JobTitle.SECURITY: "أمن وسلامة",
    }

    class Meta:
        model = Employee

        fields = [
            "employee_number",
            "full_name",
            "operational_section",
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

            "operational_section": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["operational_section"].required = True
        self.fields["operational_section"].error_messages = {
            "required": "يجب اختيار القسم التشغيلي.",
            "invalid_choice": "يجب اختيار القسم التشغيلي: رجالي أو نسائي.",
        }
        self.fields["operational_section"].choices = [
            ("", "اختر القسم التشغيلي"),
            *Employee.OperationalSection.choices,
        ]
        if self._selected_operational_section() == Employee.OperationalSection.FEMALE:
            self.fields["job_title"].choices = self._female_job_title_choices()

    def _selected_operational_section(self):
        if self.is_bound:
            return self.data.get(self.add_prefix("operational_section"), "")
        return self.instance.operational_section

    @classmethod
    def _female_job_title_choices(cls):
        return [
            (value, cls.FEMALE_JOB_TITLE_LABELS.get(value, label))
            for value, label in Employee.JobTitle.choices
        ]

    @property
    def job_title_labels(self):
        return {
            "male": {
                str(value): label
                for value, label in Employee.JobTitle.choices
            },
            "female": {
                str(value): label
                for value, label in self.FEMALE_JOB_TITLE_LABELS.items()
            },
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

    def clean_operational_section(self):
        operational_section = str(
            self.cleaned_data.get("operational_section") or ""
        ).strip().lower()
        if operational_section not in {
            Employee.OperationalSection.MALE,
            Employee.OperationalSection.FEMALE,
        }:
            raise ValidationError("يجب اختيار القسم التشغيلي: رجالي أو نسائي.")
        return operational_section

    def clean_national_id(self):
        national_id = (
            self.cleaned_data.get("national_id") or ""
        ).strip()

        return national_id

    def clean_phone_number(self):
        phone = (
            self.cleaned_data.get("phone_number") or ""
        ).strip()

        if phone:
            RegexValidator(
                regex=r"^\+[1-9]\d{7,14}$",
                message="أدخل رقم جوال بصيغة E.164، مثل +9665XXXXXXXX.",
            )(phone)

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