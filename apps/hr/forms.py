from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.communications.services.otp_validation import (
    OTPRecipientValidationError,
    normalize_saudi_phone_number,
)
from apps.hr.models import Employee


class EmployeeForm(forms.ModelForm):
    """
    النموذج الموحد لإضافة الموظف وتعديل بياناته.

    يدعم:
    - القسم الرجالي.
    - القسم النسائي.
    - التحقق من البيانات الأساسية.
    - توحيد تنسيق الحقول.
    """

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
            "user",
            "employee_number",
            "full_name",
            "operational_section",
            "national_id",
            "phone_number",
            "email",
            "job_title",
            "work_status",
            "is_active",
            "can_work_on_doors",
            "can_execute_maintenance",
            "hire_date",
            "notes",
        ]

        labels = {
            "operational_section": "القسم التشغيلي",
        }

        help_texts = {
            "operational_section": (
                "حدد القسم الذي يتبع له الموظف: "
                "رجالي أو نسائي."
            ),
        }

        widgets = {
            "user": forms.Select(
                attrs={
                    "class": "form-select",
                    "data-field": "user",
                }
            ),

            "employee_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "أدخل الرقم الوظيفي",
                    "autocomplete": "off",
                    "maxlength": "20",
                    "dir": "ltr",
                }
            ),

            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "أدخل الاسم الكامل",
                    "autocomplete": "name",
                }
            ),

            "operational_section": forms.Select(
                attrs={
                    "class": "form-select",
                    "data-field": "operational_section",
                }
            ),

            "national_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "رقم الهوية المكون من 10 أرقام",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                    "maxlength": "10",
                    "dir": "ltr",
                }
            ),

            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: +9665XXXXXXXX",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "maxlength": "20",
                    "dir": "ltr",
                }
            ),

            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "example@domain.com",
                    "autocomplete": "email",
                    "dir": "ltr",
                }
            ),

            "job_title": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "work_status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),

            "can_work_on_doors": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),

            "can_execute_maintenance": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),

            "hire_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),

            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "أدخل الملاحظات الإضافية",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "operational_section"
        ].required = True

        self.fields[
            "operational_section"
        ].error_messages = {
            "required": "يجب اختيار القسم التشغيلي.",
            "invalid_choice": (
                "يجب اختيار القسم التشغيلي: "
                "رجالي أو نسائي."
            ),
        }

        self.fields[
            "operational_section"
        ].choices = [
            (
                "",
                "اختر القسم التشغيلي",
            ),
            *Employee.OperationalSection.choices,
        ]

        selected_section = self._selected_operational_section()
        if selected_section == Employee.OperationalSection.FEMALE:
            self.fields["job_title"].choices = self._female_job_title_choices()

        self.fields[
            "employee_number"
        ].required = True

        self.fields[
            "full_name"
        ].required = True

        self.fields[
            "user"
        ].required = False

        self.fields[
            "national_id"
        ].required = False

        self.fields[
            "phone_number"
        ].required = False

        self.fields[
            "email"
        ].required = False

        self.fields[
            "hire_date"
        ].required = False

        self.fields[
            "notes"
        ].required = False

        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "aria-label",
                str(
                    field.label
                    or field_name
                ),
            )

        if self.instance.pk:
            self.fields[
                "employee_number"
            ].widget.attrs[
                "data-original-value"
            ] = self.instance.employee_number

    def _selected_operational_section(self) -> str:
        if self.is_bound:
            return str(
                self.data.get(
                    self.add_prefix("operational_section"),
                    "",
                )
            )

        return self.instance.operational_section

    @classmethod
    def _female_job_title_choices(cls) -> list[tuple[str, str]]:
        return [
            (
                value,
                cls.FEMALE_JOB_TITLE_LABELS.get(
                    value,
                    label,
                ),
            )
            for value, label in Employee.JobTitle.choices
        ]

    @property
    def job_title_labels(self) -> dict[str, dict[str, str]]:
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

    def clean_employee_number(
        self,
    ) -> str:
        employee_number = str(
            self.cleaned_data.get(
                "employee_number"
            )
            or ""
        ).strip()

        if not employee_number:
            raise ValidationError(
                "الرقم الوظيفي مطلوب."
            )

        duplicate_query = (
            Employee.objects.filter(
                employee_number=employee_number
            )
        )

        if self.instance.pk:
            duplicate_query = (
                duplicate_query.exclude(
                    pk=self.instance.pk
                )
            )

        if duplicate_query.exists():
            raise ValidationError(
                "الرقم الوظيفي مسجل لموظف آخر."
            )

        return employee_number

    def clean_full_name(
        self,
    ) -> str:
        full_name = str(
            self.cleaned_data.get(
                "full_name"
            )
            or ""
        ).strip()

        if not full_name:
            raise ValidationError(
                "الاسم الكامل مطلوب."
            )

        return " ".join(
            full_name.split()
        )

    def clean_operational_section(
        self,
    ) -> str:
        operational_section = str(
            self.cleaned_data.get(
            "operational_section"
            )
            or ""
        ).strip().lower()

        valid_sections = {
            Employee.OperationalSection.MALE,
            Employee.OperationalSection.FEMALE,
        }

        if operational_section not in valid_sections:
            raise ValidationError(
                "يجب اختيار القسم التشغيلي: "
                "رجالي أو نسائي."
            )

        return operational_section

    def clean_national_id(
        self,
    ) -> str:
        national_id = str(
            self.cleaned_data.get(
                "national_id"
            )
            or ""
        ).strip()

        if not national_id:
            return ""

        if (
            len(national_id) != 10
            or not national_id.isdigit()
        ):
            raise ValidationError(
                "رقم الهوية يجب أن يتكون "
                "من 10 أرقام."
            )

        duplicate_query = (
            Employee.objects.filter(
                national_id=national_id
            )
        )

        if self.instance.pk:
            duplicate_query = (
                duplicate_query.exclude(
                    pk=self.instance.pk
                )
            )

        if duplicate_query.exists():
            raise ValidationError(
                "رقم الهوية مسجل لموظف آخر."
            )

        return national_id

    def clean_phone_number(
        self,
    ) -> str:
        phone_number = str(
            self.cleaned_data.get(
                "phone_number"
            )
            or ""
        ).strip()
        if not phone_number:
            return ""
        try:
            return normalize_saudi_phone_number(phone_number)
        except OTPRecipientValidationError as exc:
            raise ValidationError(
                "أدخل رقم جوال سعودي صحيحًا، مثل 0501234567 أو +966501234567."
            ) from exc

    def clean_email(
        self,
    ) -> str:
        return str(
            self.cleaned_data.get(
                "email"
            )
            or ""
        ).strip().lower()

    def clean(self) -> dict:
        cleaned_data = super().clean()

        work_status = cleaned_data.get(
            "work_status"
        )

        is_active = cleaned_data.get(
            "is_active"
        )

        can_work_on_doors = cleaned_data.get(
            "can_work_on_doors"
        )

        if (
            work_status
            and work_status
            != Employee.WorkStatus.ACTIVE
        ):
            cleaned_data[
                "is_active"
            ] = False

            cleaned_data[
                "can_work_on_doors"
            ] = False

        if (
            is_active
            and work_status
            != Employee.WorkStatus.ACTIVE
        ):
            self.add_error(
                "is_active",
                (
                    "لا يمكن تفعيل الموظف بينما "
                    "حالته الوظيفية ليست على رأس العمل."
                ),
            )

        if (
            can_work_on_doors
            and not cleaned_data.get(
                "is_active"
            )
        ):
            self.add_error(
                "can_work_on_doors",
                (
                    "لا يمكن السماح بالتسكين لموظف "
                    "غير نشط في النظام."
                ),
            )

        return cleaned_data


class EmployeeCreateForm(EmployeeForm):
    """
    نموذج إضافة موظف جديد.
    """

    class Meta(EmployeeForm.Meta):
        pass


class EmployeeUpdateForm(EmployeeForm):
    """
    نموذج تعديل بيانات موظف موجود.
    """

    class Meta(EmployeeForm.Meta):
        pass
