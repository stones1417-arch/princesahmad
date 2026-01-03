from django.db import models
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan


class DoorAssignment(models.Model):
    """
    توزيع الموظف على باب داخل وردية
    """
    shift_plan = models.ForeignKey(ShiftPlan, on_delete=models.CASCADE)
    door = models.ForeignKey(Door, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    is_supervisor = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee} @ {self.door}"
