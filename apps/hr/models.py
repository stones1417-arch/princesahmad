from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class Employee(models.Model):
    """
    ملف الموظف الإداري والتشغيلي.

    القواعد:
    - الرقم الوظيفي فريد.
    - رقم الهوية، عند إدخاله، يتكون من 10 أرقام ولا يتكرر.
    - الموظف غير النشط أو غير الموجود على رأس العمل لا يُسكّن.
    - الحذف الافتراضي حذف آمن، ولا يزيل السجل من قاعدة البيانات.
    """

    class JobTitle(models.TextChoices):
        CHAIRMAN_OFFICE = (
            "chairman_office",
            "مكتب معالي: رئيس مجلس الإدارة",
        )
        CEO_OFFICE = "ceo_office", "مكتب الرئيس التنفيذي"
        DEPUTY_CEO_OPERATIONS = (
            "deputy_ceo_operations",
            "نائب الرئيس التنفيذي للتشغيل للمسجد النبوي الشريف",
        )

        GM = "gm", "المدير العام"
        DOORS_HEAD = "doors_head", "رئيس قسم الأبواب"
        DOORS_DEPUTY = "doors_deputy", "وكيل رئيس قسم الأبواب"
        SENIOR_ADMIN = "senior_admin", "كبير الإداريين للأبواب"
        ADMIN_SECRETARY = "admin_secretary", "سكرتير إداري"

        FAJR_SUPERVISOR = "fajr_supervisor", "مشرف وردية الفجر"
        DUHA_SUPERVISOR = "duha_supervisor", "مشرف وردية الضحى"
        EVENING_SUPERVISOR = "evening_supervisor", "مشرف وردية مسائية"
        SUPPORT_SUPERVISOR = "support_supervisor", "مشرف وردية مساندة"

        FAJR_DEPUTY = "fajr_deputy", "نائب مشرف الفجر"
        DUHA_DEPUTY = "duha_deputy", "نائب مشرف الضحى"
        EVENING_DEPUTY = "evening_deputy", "نائب مشرف المسائية"

        TECH_SECRETARY = "tech_secretary", "سكرتير فني"
        TECHNICIAN = "technician", "فني صيانة"
        MONITOR = "monitor", "مراقب أبواب"
        SECURITY = "security", "أمن وسلامة"

    class WorkStatus(models.TextChoices):
        ACTIVE = "active", "على رأس العمل"
        INACTIVE = "inactive", "غير نشط"
        VACATION = "vacation", "إجازة"
        SUSPENDED = "suspended", "موقوف مؤقتًا"
        TRANSFERRED = "transferred", "منقول"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee",
        verbose_name="حساب المستخدم",
    )

    employee_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="الرقم الوظيفي",
    )

    full_name = models.CharField(
        max_length=150,
        db_index=True,
        verbose_name="الاسم الكامل",
    )

    national_id = models.CharField(
        max_length=10,
        blank=True,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r"^\d{10}$",
                message="رقم الهوية يجب أن يتكون من 10 أرقام.",
            ),
        ],
        verbose_name="رقم الهوية",
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?\d{8,15}$",
                message=(
                    "رقم الجوال يجب أن يحتوي على أرقام فقط "
                    "ويمكن أن يبدأ بعلامة +."
                ),
            ),
        ],
        verbose_name="رقم الجوال",
    )

    email = models.EmailField(
        blank=True,
        verbose_name="البريد الإلكتروني",
    )

    job_title = models.CharField(
        max_length=50,
        choices=JobTitle.choices,
        default=JobTitle.MONITOR,
        db_index=True,
        verbose_name="المسمى الوظيفي",
    )

    work_status = models.CharField(
        max_length=20,
        choices=WorkStatus.choices,
        default=WorkStatus.ACTIVE,
        db_index=True,
        verbose_name="حالة الموظف",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشط في النظام",
    )

    can_work_on_doors = models.BooleanField(
        default=True,
        verbose_name="يمكن تسكينه على الأبواب",
    )

    can_execute_maintenance = models.BooleanField(
        default=False,
        verbose_name="يمكنه تنفيذ الصيانة",
    )

    hire_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ المباشرة",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإضافة",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        verbose_name = "موظف"
        verbose_name_plural = "الموظفون"

        ordering = [
            "employee_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "national_id",
                ],
                condition=~models.Q(
                    national_id="",
                ),
                name="unique_non_empty_employee_national_id",
            ),
        ]

        indexes = [
            models.Index(
                fields=["employee_number"],
                name="hr_employee_number_idx",
            ),
            models.Index(
                fields=["full_name"],
                name="hr_employee_name_idx",
            ),
            models.Index(
                fields=["job_title"],
                name="hr_employee_job_idx",
            ),
            models.Index(
                fields=["work_status"],
                name="hr_employee_status_idx",
            ),
            models.Index(
                fields=["is_active"],
                name="hr_employee_active_idx",
            ),
            models.Index(
                fields=["national_id"],
                name="hr_employee_nid_idx",
            ),
        ]

        permissions = [
            (
                "can_view_employee_dashboard",
                "يمكن عرض لوحة الموظفين",
            ),
            (
                "can_activate_employee",
                "يمكن تفعيل الموظف",
            ),
            (
                "can_deactivate_employee",
                "يمكن تعطيل الموظف",
            ),
            (
                "can_hard_delete_employee",
                "يمكن حذف الموظف نهائيًا",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.full_name} - "
            f"{self.get_job_title_display()}"
        )

    @property
    def display_status(self) -> str:
        return self.get_work_status_display()

    @property
    def is_available_for_assignment(self) -> bool:
        """
        الموظف متاح للتسكين فقط عندما تتحقق الشروط كلها.
        """

        return (
            self.is_active
            and self.work_status == self.WorkStatus.ACTIVE
            and self.can_work_on_doors
        )

    @property
    def is_maintenance_member(self) -> bool:
        return (
            self.is_active
            and self.can_execute_maintenance
        )

    def clean(self) -> None:
        """
        التحقق من صحة بيانات الموظف.
        """

        super().clean()

        errors: dict[str, str] = {}

        self.employee_number = str(
            self.employee_number or ""
        ).strip()

        self.full_name = str(
            self.full_name or ""
        ).strip()

        self.national_id = str(
            self.national_id or ""
        ).strip()

        self.phone_number = str(
            self.phone_number or ""
        ).strip()

        self.email = str(
            self.email or ""
        ).strip()

        if not self.employee_number:
            errors["employee_number"] = (
                "الرقم الوظيفي مطلوب."
            )

        if not self.full_name:
            errors["full_name"] = (
                "الاسم الكامل مطلوب."
            )

        if self.national_id:
            if (
                len(self.national_id) != 10
                or not self.national_id.isdigit()
            ):
                errors["national_id"] = (
                    "رقم الهوية يجب أن يتكون من 10 أرقام."
                )

            duplicate_query = Employee.objects.filter(
                national_id=self.national_id,
            )

            if self.pk:
                duplicate_query = duplicate_query.exclude(
                    pk=self.pk,
                )

            if duplicate_query.exists():
                errors["national_id"] = (
                    "رقم الهوية مسجل لموظف آخر."
                )

        if (
            self.work_status != self.WorkStatus.ACTIVE
            and self.is_active
        ):
            errors["is_active"] = (
                "لا يمكن اعتبار الموظف نشطًا في النظام "
                "بينما حالته الوظيفية ليست على رأس العمل."
            )

        if errors:
            raise ValidationError(
                errors
            )

    def save(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        حفظ الموظف مع المحافظة على القيمة الصريحة لـ is_active.

        لا تتم إعادة الموظف إلى نشط تلقائيًا لمجرد أن
        work_status تساوي ACTIVE، حتى يمكن إنشاء موظف غير نشط
        واختبار منعه من التسكين.
        """

        if (
            self.work_status
            != self.WorkStatus.ACTIVE
        ):
            self.is_active = False

        if (
            self.job_title
            == self.JobTitle.TECHNICIAN
        ):
            self.can_execute_maintenance = True

        self.full_clean()

        super().save(
            *args,
            **kwargs,
        )

    def delete(
        self,
        using=None,
        keep_parents: bool = False,
    ):
        """
        حذف آمن للموظف.

        لا يتم حذف السجل فعليًا، وإنما:
        - تعطيل الموظف.
        - تغيير حالته إلى غير نشط.
        - منع تسكينه على الأبواب.
        - تعطيل حساب المستخدم المرتبط، إن وجد.
        """

        database_alias = (
            using
            or self._state.db
        )

        self.is_active = False
        self.work_status = self.WorkStatus.INACTIVE
        self.can_work_on_doors = False

        self.save(
            using=database_alias,
            update_fields=[
                "is_active",
                "work_status",
                "can_work_on_doors",
                "updated_at",
            ],
        )

        if (
            self.user_id
            and self.user
            and self.user.is_active
        ):
            self.user.is_active = False
            self.user.save(
                using=database_alias,
                update_fields=[
                    "is_active",
                ],
            )

        return (
            0,
            {
                self._meta.label: 0,
            },
        )

    def hard_delete(
        self,
        using=None,
        keep_parents: bool = False,
    ):
        """
        حذف نهائي صريح.

        يجب استدعاؤه فقط من خدمة إدارية محمية بصلاحية خاصة.
        """

        return super().delete(
            using=using,
            keep_parents=keep_parents,
        )
