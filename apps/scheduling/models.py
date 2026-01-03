from django.db import models
from apps.hr.models import Employee


class ShiftType(models.Model):
    """
    أنواع الورديات (فجر – ضحى – مسائية – مساندة)
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class ShiftPlan(models.Model):
    """
    خطة وردية ليوم محدد
    """
    date = models.DateField()
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT)

    class Meta:
        unique_together = ('date', 'shift_type')

    def __str__(self):
        return f"{self.shift_type} - {self.date}"


class ShiftAssignment(models.Model):
    """
    تسكين الموظف في وردية
    """
    shift_plan = models.ForeignKey(ShiftPlan, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)

    class Meta:
        unique_together = ('shift_plan', 'employee')

    def __str__(self):
        return f"{self.employee} → {self.shift_plan}"
