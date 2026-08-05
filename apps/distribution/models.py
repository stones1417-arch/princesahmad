from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.hr.models import Employee
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan


class DoorAssignment(models.Model):
    """
    توزيع الموظف على باب معين داخل وردية.

    سجل عمليات الإنشاء والتعديل والنقل والإلغاء
    يُحفظ مركزيًا داخل:
    apps.audit.models.AssignmentHistory
    """

    class Role(models.TextChoices):
        SUPERVISOR = "supervisor", "مشرف باب"
        MONITOR = "monitor", "مراقب باب"
        SUPPORT = "support", "مساند"
        TECHNICIAN = "technician", "فني صيانة"

    shift_plan = models.ForeignKey(
        ShiftPlan,
        on_delete=models.CASCADE,
        related_name="door_assignments",
        verbose_name="الوردية",
        db_index=True,
    )

    door = models.ForeignKey(
        Door,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="الباب",
        db_index=True,
    )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="door_assignments",
        verbose_name="الموظف",
        db_index=True,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MONITOR,
        verbose_name="الدور على الباب",
        db_index=True,
    )

    is_supervisor = models.BooleanField(
        default=False,
        verbose_name="مشرف الباب",
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="توزيع نشط",
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_door_assignments",
        verbose_name="تم التوزيع بواسطة",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ التوزيع",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        verbose_name = "توزيع باب"
        verbose_name_plural = "توزيعات الأبواب"

        ordering = [
            "door__door_number",
            "-is_supervisor",
            "employee__employee_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "door",
                    "employee",
                ],
                name="unique_employee_per_door_in_shift",
            ),
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "employee",
                ],
                condition=models.Q(
                    is_active=True,
                ),
                name="unique_active_employee_assignment_per_shift",
            ),
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "door",
                ],
                condition=models.Q(
                    is_supervisor=True,
                    is_active=True,
                ),
                name="unique_active_supervisor_per_door_shift",
            ),
        ]

        indexes = [
            models.Index(
                fields=["shift_plan"],
                name="dist_assign_shift_idx",
            ),
            models.Index(
                fields=["door"],
                name="dist_assign_door_idx",
            ),
            models.Index(
                fields=["employee"],
                name="dist_assign_employee_idx",
            ),
            models.Index(
                fields=["role"],
                name="dist_assign_role_idx",
            ),
            models.Index(
                fields=["is_active"],
                name="dist_assign_active_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "door",
                    "is_active",
                ],
                name="dist_shift_door_active_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "employee",
                    "is_active",
                ],
                name="dist_shift_emp_active_idx",
            ),
        ]

        permissions = [
            (
                "can_assign_door_employee",
                "يمكن توزيع موظف على باب",
            ),
            (
                "can_assign_door_supervisor",
                "يمكن تعيين مشرف باب",
            ),
            (
                "can_view_distribution_dashboard",
                "يمكن عرض لوحة توزيع الأبواب",
            ),
            (
                "can_auto_assign_employees",
                "يمكن تنفيذ التوزيع التلقائي",
            ),
            (
                "can_rebalance_distribution",
                "يمكن إعادة توازن التوزيع",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.employee.full_name} – "
            f"{self.door} "
            f"({self.get_role_display()})"
        )

    def clean(self) -> None:
        """
        التحقق من القواعد الأساسية للتوزيع.
        """

        super().clean()

        errors: dict[str, str] = {}

        if self.shift_plan_id:
            if not self.shift_plan.is_active:
                errors["shift_plan"] = (
                    "لا يمكن التوزيع على وردية غير نشطة."
                )

            if getattr(
                self.shift_plan,
                "is_finished",
                False,
            ):
                errors["shift_plan"] = (
                    "لا يمكن التوزيع على وردية منتهية."
                )

        if self.door_id:
            if not self.door.is_active:
                errors["door"] = (
                    "لا يمكن التوزيع على باب غير نشط."
                )

        if self.employee_id:
            if not self.employee.is_active:
                errors["employee"] = (
                    "لا يمكن تسكين موظف غير نشط."
                )

            elif (
                self.employee.work_status
                != Employee.WorkStatus.ACTIVE
            ):
                errors["employee"] = (
                    "لا يمكن تسكين موظف ليس على رأس العمل."
                )

            elif not self.employee.can_work_on_doors:
                errors["employee"] = (
                    "الموظف غير مصرح له بالعمل على الأبواب."
                )

        if (
            self.employee_id
            and self.role == self.Role.TECHNICIAN
            and not self.employee.can_execute_maintenance
        ):
            errors["role"] = (
                "الموظف ليس ضمن فريق الصيانة."
            )

        if self.role == self.Role.SUPERVISOR:
            self.is_supervisor = True

        elif self.is_supervisor:
            self.role = self.Role.SUPERVISOR

        else:
            self.is_supervisor = False

        if (
            self.shift_plan_id
            and self.employee_id
            and self.is_active
        ):
            employee_assignment_query = (
                DoorAssignment.objects.filter(
                    shift_plan_id=self.shift_plan_id,
                    employee_id=self.employee_id,
                    is_active=True,
                )
            )

            if self.pk:
                employee_assignment_query = (
                    employee_assignment_query.exclude(
                        pk=self.pk,
                    )
                )

            if employee_assignment_query.exists():
                errors["employee"] = (
                    "الموظف مسكن مسبقًا في هذه الوردية."
                )

        if (
            self.shift_plan_id
            and self.door_id
            and self.is_supervisor
            and self.is_active
        ):
            supervisor_query = (
                DoorAssignment.objects.filter(
                    shift_plan_id=self.shift_plan_id,
                    door_id=self.door_id,
                    is_supervisor=True,
                    is_active=True,
                )
            )

            if self.pk:
                supervisor_query = supervisor_query.exclude(
                    pk=self.pk,
                )

            if supervisor_query.exists():
                errors["is_supervisor"] = (
                    "يوجد مشرف نشط مسجل مسبقًا على هذا الباب."
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
        حفظ التوزيع بعد تنفيذ التحقق الكامل.
        """

        self.full_clean()

        super().save(
            *args,
            **kwargs,
        )

    @property
    def is_technician(self) -> bool:
        return (
            self.role
            == self.Role.TECHNICIAN
        )

    @property
    def is_monitor(self) -> bool:
        return (
            self.role
            == self.Role.MONITOR
        )

    @property
    def is_support(self) -> bool:
        return (
            self.role
            == self.Role.SUPPORT
        )

    @property
    def role_display(self) -> str:
        return self.get_role_display()