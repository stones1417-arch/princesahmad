from django.db import models
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan


class DoorStatus(models.Model):
    """
    حالة الباب أثناء الوردية
    """
    STATUS_CHOICES = [
        ('open', 'مفتوح'),
        ('closed', 'مغلق'),
        ('maintenance', 'صيانة'),
    ]

    door = models.ForeignKey(Door, on_delete=models.PROTECT)
    shift_plan = models.ForeignKey(ShiftPlan, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.door} - {self.status}"


class MaintenanceRequest(models.Model):
    """
    طلب صيانة
    """
    door = models.ForeignKey(Door, on_delete=models.PROTECT)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"صيانة {self.door}"
