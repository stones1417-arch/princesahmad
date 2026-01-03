from django.conf import settings
from django.db import models


class Employee(models.Model):
    """
    الملف الوظيفي للموظف
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    employee_number = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.employee_number})"
