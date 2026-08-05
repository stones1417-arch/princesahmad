from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class ShiftAssignment(models.Model):
    """
    تسكين الموظف في وردية مع تحديد دوره التشغيلي.
    """

    class OperationalRole(models.TextChoices):
        SHIFT_HEAD = "shift_head", "رئيس الوردية"
        SHIFT_DEPUTY = "shift_deputy", "نائب الوردية"
        SUPERVISOR = "supervisor", "مشرف"
        MONITOR = "monitor", "مراقب"
        TECHNICIAN = "technician", "فني"
        ADMIN = "admin", "إداري"
        SENIOR_ADMIN = "senior_admin", "كبير الإداريين"
        SUPPORT = "support", "مساند"

    shift_plan = models.ForeignKey(
        "scheduling.ShiftPlan",
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="الوردية",
    )

    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="shift_assignments",
        verbose_name="الموظف",
    )

    role = models.CharField(
        max_length=30,
        choices=OperationalRole.choices,
        default=OperationalRole.MONITOR,
        db_index=True,
        verbose_name="الدور التشغيلي",
    )

    is_confirmed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="تم التأكيد",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ التسكين",
    )

    class Meta:
        ordering = [
            "shift_plan",
            "role",
            "employee__employee_number",
        ]

        verbose_name = "تسكين موظف"
        verbose_name_plural = "تسكين الموظفين"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "employee",
                ],
                name="unique_employee_per_shift_plan",
            ),
        ]

        indexes = [
            models.Index(
                fields=["shift_plan"],
                name="shift_assignment_plan_idx",
            ),
            models.Index(
                fields=["employee"],
                name="shift_assignment_emp_idx",
            ),
            models.Index(
                fields=["role"],
                name="shift_assignment_role_idx",
            ),
            models.Index(
                fields=["is_confirmed"],
                name="shift_assignment_conf_idx",
            ),
        ]

        permissions = [
            (
                "can_assign_employee",
                "يمكن تسكين الموظف في وردية",
            ),
            (
                "can_confirm_assignment",
                "يمكن تأكيد التسكين",
            ),
        ]

    def clean(self) -> None:
        """
        التحقق من صلاحية الموظف والوردية قبل التسكين.
        """
        super().clean()

        errors: dict[str, str] = {}

        if self.shift_plan_id:
            shift_plan = self.shift_plan

            if shift_plan.is_finished:
                errors["shift_plan"] = (
                    "لا يمكن تسكين موظف في وردية منتهية."
                )

        if self.employee_id:
            employee = self.employee

            if not employee.is_active:
                errors["employee"] = (
                    "لا يمكن تسكين موظف غير نشط."
                )

            if not getattr(
                employee,
                "can_work_on_doors",
                True,
            ):
                errors["employee"] = (
                    "الموظف لا يملك صلاحية العمل على الأبواب."
                )

        if (
            self.shift_plan_id
            and self.employee_id
        ):
            duplicate_assignment = (
                ShiftAssignment.objects
                .exclude(pk=self.pk)
                .filter(
                    shift_plan_id=self.shift_plan_id,
                    employee_id=self.employee_id,
                )
            )

            if duplicate_assignment.exists():
                errors["employee"] = (
                    "الموظف مسكن مسبقًا في هذه الوردية."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        تشغيل التحقق الكامل قبل الحفظ.
        """
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self) -> str:
        return (
            f"{self.employee} → "
            f"{self.shift_plan} "
            f"({self.get_role_display()})"
        )