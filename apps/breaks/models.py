from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.hr.models import Employee
from apps.scheduling.models import ShiftType


class Break(models.Model):
    """
    راحة الموظف الأسبوعية حسب الوردية والمسمى التشغيلي.

    القواعد:
    - الموظف يجب أن يكون نشطًا.
    - لا يسمح بأكثر من راحة نشطة للموظف في الوردية نفسها.
    - لا يسمح بتفعيل راحة مرتبطة بوردية غير نشطة، إن كان
      نموذج ShiftType يحتوي على الحقل is_active.
    """

    class RestDays(models.TextChoices):
        FRIDAY_SATURDAY = (
            "friday_saturday",
            "الجمعة - السبت",
        )
        SATURDAY_SUNDAY = (
            "saturday_sunday",
            "السبت - الأحد",
        )
        SUNDAY_MONDAY = (
            "sunday_monday",
            "الأحد - الاثنين",
        )
        MONDAY_TUESDAY = (
            "monday_tuesday",
            "الاثنين - الثلاثاء",
        )
        TUESDAY_WEDNESDAY = (
            "tuesday_wednesday",
            "الثلاثاء - الأربعاء",
        )
        WEDNESDAY_THURSDAY = (
            "wednesday_thursday",
            "الأربعاء - الخميس",
        )
        THURSDAY_FRIDAY = (
            "thursday_friday",
            "الخميس - الجمعة",
        )

    class BreakJobTitle(models.TextChoices):
        SHIFT_HEAD = (
            "shift_head",
            "رئيس الوردية",
        )
        SHIFT_DEPUTY = (
            "shift_deputy",
            "نائب الوردية",
        )
        SUPERVISOR = (
            "supervisor",
            "مشرف",
        )
        MONITOR = (
            "monitor",
            "مراقب",
        )
        SENIOR_ADMIN = (
            "senior_admin",
            "كبير الإداريين",
        )
        ADMIN = (
            "admin",
            "إداري",
        )
        TECHNICIAN = (
            "technician",
            "فني",
        )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="weekly_breaks",
        verbose_name="الموظف",
        db_index=True,
    )

    shift_type = models.ForeignKey(
        ShiftType,
        on_delete=models.PROTECT,
        related_name="weekly_breaks",
        verbose_name="نوع الوردية",
        db_index=True,
    )

    job_title = models.CharField(
        max_length=30,
        choices=BreakJobTitle.choices,
        verbose_name="المسمى في الوردية",
        db_index=True,
    )

    rest_days = models.CharField(
        max_length=40,
        choices=RestDays.choices,
        verbose_name="أيام الراحة",
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
        db_index=True,
    )

    class Meta:
        verbose_name = "راحة"
        verbose_name_plural = "الراحات"

        ordering = [
            "shift_type__name",
            "rest_days",
            "employee__employee_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "employee",
                    "shift_type",
                ],
                condition=models.Q(
                    is_active=True,
                ),
                name=(
                    "unique_active_break_"
                    "per_employee_shift"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "employee",
                ],
                name="break_employee_idx",
            ),
            models.Index(
                fields=[
                    "shift_type",
                ],
                name="break_shift_type_idx",
            ),
            models.Index(
                fields=[
                    "job_title",
                ],
                name="break_job_title_idx",
            ),
            models.Index(
                fields=[
                    "rest_days",
                ],
                name="break_rest_days_idx",
            ),
            models.Index(
                fields=[
                    "is_active",
                ],
                name="break_active_idx",
            ),
            models.Index(
                fields=[
                    "shift_type",
                    "rest_days",
                    "is_active",
                ],
                name="break_shift_days_active_idx",
            ),
            models.Index(
                fields=[
                    "employee",
                    "is_active",
                ],
                name="break_employee_active_idx",
            ),
        ]

        permissions = [
            (
                "can_view_break_dashboard",
                "يمكن عرض لوحة الراحات",
            ),
            (
                "can_create_employee_break",
                "يمكن إضافة راحة موظف",
            ),
            (
                "can_update_employee_break",
                "يمكن تعديل راحة موظف",
            ),
            (
                "can_toggle_employee_break",
                "يمكن تفعيل أو تعطيل راحة موظف",
            ),
            (
                "can_delete_employee_break",
                "يمكن حذف راحة موظف",
            ),
            (
                "can_view_break_history",
                "يمكن عرض سجل تغييرات الراحات",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.employee.full_name} - "
            f"{self.get_job_title_display()} - "
            f"{self.shift_type.name} - "
            f"{self.get_rest_days_display()}"
        )

    @property
    def status_label(self) -> str:
        """
        الاسم العربي لحالة السجل.
        """

        return (
            "نشط"
            if self.is_active
            else "غير نشط"
        )

    @property
    def operational_section(self) -> str:
        """القسم التشغيلي الموروث من سجل الموظف."""
        return str(
            getattr(self.employee, "operational_section", "")
            or ""
        ).strip().lower()

    @property
    def operational_section_label(self) -> str:
        """الاسم العربي للقسم التشغيلي."""
        return dict(
            Employee.OperationalSection.choices
        ).get(
            self.operational_section,
            "غير محدد",
        )

    def clean(self) -> None:
        """
        التحقق من قواعد الراحة قبل الحفظ.
        """

        super().clean()

        errors: dict[str, str] = {}

        if self.employee_id:
            employee_is_active = bool(
                getattr(
                    self.employee,
                    "is_active",
                    False,
                )
            )

            if not employee_is_active:
                errors["employee"] = (
                    "لا يمكن إضافة أو تفعيل راحة "
                    "لموظف غير نشط."
                )

        if self.shift_type_id and self.is_active:
            shift_is_active = getattr(
                self.shift_type,
                "is_active",
                True,
            )

            if shift_is_active is False:
                errors["shift_type"] = (
                    "لا يمكن ربط راحة نشطة "
                    "بنوع وردية غير نشط."
                )

        if (
            self.employee_id
            and self.shift_type_id
            and self.is_active
        ):
            duplicate_query = Break.objects.filter(
                employee_id=self.employee_id,
                shift_type_id=self.shift_type_id,
                is_active=True,
            )

            if self.pk:
                duplicate_query = duplicate_query.exclude(
                    pk=self.pk,
                )

            if duplicate_query.exists():
                errors["employee"] = (
                    "هذا الموظف لديه راحة نشطة "
                    "مسجلة مسبقًا في الوردية نفسها."
                )

        if errors:
            raise ValidationError(errors)

    def save(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        التحقق الكامل قبل كل عملية حفظ.
        """

        self.full_clean()
        super().save(*args, **kwargs)

    def to_snapshot(self) -> dict[str, Any]:
        """
        إنشاء لقطة قابلة للحفظ داخل سجل التدقيق.
        """

        return {
            "break_id": self.pk,
            "employee_id": self.employee_id,
            "employee_number": (
                self.employee.employee_number
                if self.employee_id
                else ""
            ),
            "employee_name": (
                self.employee.full_name
                if self.employee_id
                else ""
            ),
            "operational_section": (
                self.operational_section
            ),
            "operational_section_label": (
                self.operational_section_label
            ),
            "shift_type_id": self.shift_type_id,
            "shift_type_name": (
                self.shift_type.name
                if self.shift_type_id
                else ""
            ),
            "job_title": self.job_title,
            "job_title_label": (
                self.get_job_title_display()
                if self.job_title
                else ""
            ),
            "rest_days": self.rest_days,
            "rest_days_label": (
                self.get_rest_days_display()
                if self.rest_days
                else ""
            ),
            "is_active": self.is_active,
            "status_label": self.status_label,
            "notes": self.notes or "",
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at
                else None
            ),
        }


class BreakHistory(models.Model):
    """
    سجل تدقيق عمليات الراحات.

    يحفظ:
    - الإنشاء.
    - التعديل.
    - التفعيل.
    - التعطيل.
    - الحذف.
    - القيم السابقة والجديدة.
    - المستخدم المنفذ.
    - السبب وعنوان IP.
    """

    class Action(models.TextChoices):
        CREATE = (
            "create",
            "إنشاء راحة",
        )
        UPDATE = (
            "update",
            "تعديل راحة",
        )
        ACTIVATE = (
            "activate",
            "تفعيل راحة",
        )
        DEACTIVATE = (
            "deactivate",
            "تعطيل راحة",
        )
        DELETE = (
            "delete",
            "حذف راحة",
        )

    break_record = models.ForeignKey(
        Break,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_entries",
        verbose_name="سجل الراحة",
    )

    break_id_snapshot = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="معرف الراحة المحفوظ",
    )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="break_history_entries",
        verbose_name="الموظف",
        db_index=True,
    )

    shift_type = models.ForeignKey(
        ShiftType,
        on_delete=models.PROTECT,
        related_name="break_history_entries",
        verbose_name="نوع الوردية",
        db_index=True,
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        db_index=True,
        verbose_name="الإجراء",
    )

    old_value = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="القيمة السابقة",
    )

    new_value = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="القيمة الجديدة",
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_break_history_actions",
        verbose_name="منفذ الإجراء",
    )

    reason = models.TextField(
        blank=True,
        verbose_name="سبب الإجراء",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإجراء",
    )

    class Meta:
        verbose_name = "سجل تغيير راحة"
        verbose_name_plural = "سجل تغييرات الراحات"

        ordering = [
            "-created_at",
            "-id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "break_id_snapshot",
                    "created_at",
                ],
                name="break_hist_record_date_idx",
            ),
            models.Index(
                fields=[
                    "employee",
                    "created_at",
                ],
                name="break_hist_employee_date_idx",
            ),
            models.Index(
                fields=[
                    "shift_type",
                    "created_at",
                ],
                name="break_hist_shift_date_idx",
            ),
            models.Index(
                fields=[
                    "action",
                    "created_at",
                ],
                name="break_hist_action_date_idx",
            ),
            models.Index(
                fields=[
                    "performed_by",
                    "created_at",
                ],
                name="break_hist_user_date_idx",
            ),
        ]

        permissions = [
            (
                "can_view_break_audit_history",
                "يمكن عرض سجل تدقيق الراحات",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_action_display()} - "
            f"{self.employee.full_name} - "
            f"{self.created_at:%Y-%m-%d %H:%M}"
        )

    @property
    def action_label(self) -> str:
        return self.get_action_display()