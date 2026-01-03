from django.contrib import admin
from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'full_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('employee_number', 'full_name')
