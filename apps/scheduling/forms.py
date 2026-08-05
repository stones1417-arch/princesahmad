from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.hr.models import Employee


class ShiftAssignmentCreateForm(forms.Form):
    employee_id = forms.IntegerField()

    def clean_employee_id(self) -> int:
        emp_id = self.cleaned_data["employee_id"]
        if not Employee.objects.filter(pk=emp_id, is_active=True).exists():
            raise ValidationError("الموظف غير موجود أو غير نشط")
        return emp_id
