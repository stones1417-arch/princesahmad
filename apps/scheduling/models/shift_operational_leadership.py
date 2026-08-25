from django.conf import settings
from django.db import models


class ShiftOperationalLeadership(models.Model):
    class Responsibility(models.TextChoices):
        INCIDENT_SUPERVISOR = "incident_supervisor", "مشرف البلاغات"
        OPERATIONS_SUPERVISOR = "operations_supervisor", "مشرف العمليات"
        MAINTENANCE_SUPERVISOR = "maintenance_shift_supervisor", "مشرف الصيانة"

    shift_plan = models.ForeignKey(
        "scheduling.ShiftPlan", on_delete=models.CASCADE,
        related_name="operational_leadership", verbose_name="الوردية",
    )
    responsibility = models.CharField(
        max_length=40, choices=Responsibility.choices, db_index=True,
        verbose_name="المسؤولية",
    )
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT,
        related_name="shift_operational_leadership", verbose_name="المسؤول",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_shift_operational_leadership", verbose_name="أنشئ بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("shift_plan", "responsibility")
        verbose_name = "قيادة تشغيلية للوردية"
        verbose_name_plural = "القيادة التشغيلية للورديات"
        constraints = [models.UniqueConstraint(
            fields=("shift_plan", "responsibility"),
            name="unique_shift_operational_responsibility",
        )]

    @property
    def user(self):
        return self.employee.user

    def __str__(self):
        return f"{self.shift_plan} — {self.get_responsibility_display()}"
