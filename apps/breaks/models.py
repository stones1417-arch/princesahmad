from django.db import models
from apps.distribution.models import DoorAssignment


class Break(models.Model):
    """
    راحة الموظف أثناء الوردية
    """
    assignment = models.ForeignKey(DoorAssignment, on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"راحة {self.assignment.employee}"
