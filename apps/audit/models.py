from django.conf import settings
from django.db import models


class BaseHistoryModel(models.Model):
    """
    النموذج الأساسي لجميع سجلات المراجعة.
    """

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

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_changed",
        verbose_name="تم بواسطة",
    )

    changed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ التغيير",
    )

    change_reason = models.TextField(
        blank=True,
        verbose_name="سبب التغيير",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP",
    )

    class Meta:
        abstract = True
        ordering = [
            "-changed_at",
        ]


# ==========================================================
# Door State History
# ==========================================================

class DoorStateHistory(BaseHistoryModel):
    """
    سجل تغييرات حالة الباب.
    """

    door_shift = models.ForeignKey(
        "ops.DoorShift",
        on_delete=models.CASCADE,
        related_name="audit_state_history",
        verbose_name="حالة الباب",
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل حالة باب"
        verbose_name_plural = "سجل حالات الأبواب"

        indexes = [
            models.Index(
                fields=[
                    "door_shift",
                    "changed_at",
                ],
                name="audit_door_state_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"باب "
            f"{self.door_shift.door_number}"
        )


# ==========================================================
# Assignment History
# ==========================================================

class AssignmentHistory(BaseHistoryModel):
    """
    السجل المركزي والوحيد لعمليات توزيع الموظفين.

    يشمل:
    - إنشاء توزيع.
    - تعديل توزيع.
    - نقل موظف بين الأبواب.
    - إلغاء توزيع.
    - حذف توزيع.
    - التوزيع التلقائي.
    - إعادة التوازن.

    يجب عدم إنشاء نموذج AssignmentHistory آخر
    داخل تطبيق distribution.
    """

    assignment = models.ForeignKey(
        "distribution.DoorAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_history_entries",
        verbose_name="التوزيع",
    )

    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_assignment_history",
        verbose_name="الموظف",
        db_index=True,
    )

    door = models.ForeignKey(
        "locations.Door",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_assignment_history",
        verbose_name="الباب",
        db_index=True,
    )

    shift_plan = models.ForeignKey(
        "scheduling.ShiftPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_assignment_history",
        verbose_name="الوردية",
        db_index=True,
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل توزيع"
        verbose_name_plural = "سجل التوزيعات"

        indexes = [
            models.Index(
                fields=[
                    "assignment",
                    "changed_at",
                ],
                name="audit_assign_date_idx",
            ),
            models.Index(
                fields=[
                    "employee",
                    "changed_at",
                ],
                name="audit_assign_emp_date_idx",
            ),
            models.Index(
                fields=[
                    "door",
                    "changed_at",
                ],
                name="audit_assign_door_date_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "changed_at",
                ],
                name="audit_assign_shift_date_idx",
            ),
        ]

    def __str__(self):
        if self.employee_id:
            return (
                f"سجل توزيع "
                f"{self.employee.full_name}"
            )

        return (
            f"سجل توزيع رقم "
            f"{self.pk}"
        )


# ==========================================================
# Maintenance Status History
# ==========================================================

class MaintenanceStatusHistory(BaseHistoryModel):
    """
    سجل تغييرات حالات طلبات الصيانة.
    """

    maintenance_request = models.ForeignKey(
        "ops.MaintenanceRequest",
        on_delete=models.CASCADE,
        related_name="audit_status_history",
        verbose_name="طلب الصيانة",
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل حالة الصيانة"
        verbose_name_plural = "سجل حالات الصيانة"

        indexes = [
            models.Index(
                fields=[
                    "maintenance_request",
                    "changed_at",
                ],
                name="audit_maint_status_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"صيانة "
            f"{self.maintenance_request_id}"
        )


# ==========================================================
# Incident Status History
# ==========================================================

class IncidentStatusHistory(BaseHistoryModel):
    """
    سجل تغييرات حالات البلاغات.
    """

    incident = models.ForeignKey(
        "ops.Incident",
        on_delete=models.CASCADE,
        related_name="audit_status_history",
        verbose_name="البلاغ",
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل البلاغ"
        verbose_name_plural = "سجل البلاغات"

        indexes = [
            models.Index(
                fields=[
                    "incident",
                    "changed_at",
                ],
                name="audit_inc_status_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"بلاغ "
            f"{self.incident_id}"
        )


# ==========================================================
# Shift Plan History
# ==========================================================

class ShiftPlanHistory(BaseHistoryModel):
    """
    سجل العمليات التي تتم على الوردية.
    """

    class Action(models.TextChoices):
        CREATED = "created", "إنشاء"
        ACTIVATED = "activated", "تفعيل"
        UPDATED = "updated", "تعديل"
        FINISHED = "finished", "إنهاء"
        CANCELLED = "cancelled", "إلغاء"
        REOPENED = "reopened", "إعادة فتح"

    shift_plan = models.ForeignKey(
        "scheduling.ShiftPlan",
        on_delete=models.CASCADE,
        related_name="audit_history_entries",
        verbose_name="الوردية",
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices,
        db_index=True,
        verbose_name="الإجراء",
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل الوردية"
        verbose_name_plural = "سجل الورديات"

        indexes = [
            models.Index(
                fields=[
                    "shift_plan",
                    "action",
                    "changed_at",
                ],
                name="audit_shift_action_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_action_display()} - "
            f"{self.shift_plan}"
        )


# ==========================================================
# Report Approval History
# ==========================================================

class ReportApprovalHistory(BaseHistoryModel):
    """
    سجل إجراءات اعتماد التقارير.
    """

    class Action(models.TextChoices):
        SUBMITTED = "submitted", "رفع للاعتماد"
        APPROVED = "approved", "اعتماد"
        REJECTED = "rejected", "رفض"
        RETURNED = "returned", "إعادة للمراجعة"
        REVOKED = "revoked", "سحب الاعتماد"

    report = models.ForeignKey(
        "reporting.ShiftReport",
        on_delete=models.CASCADE,
        related_name="audit_approval_history",
        verbose_name="التقرير",
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices,
        db_index=True,
        verbose_name="الإجراء",
    )

    class Meta(BaseHistoryModel.Meta):
        verbose_name = "سجل اعتماد التقرير"
        verbose_name_plural = "سجل اعتماد التقارير"

        indexes = [
            models.Index(
                fields=[
                    "report",
                    "action",
                    "changed_at",
                ],
                name="audit_report_action_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_action_display()} - "
            f"{self.report}"
        )