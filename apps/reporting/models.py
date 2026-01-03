from django.db import models
from apps.scheduling.models import ShiftPlan


class ShiftReport(models.Model):
    """
    تقرير وردية
    """
    shift_plan = models.ForeignKey(ShiftPlan, on_delete=models.CASCADE)
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"تقرير {self.shift_plan}"
