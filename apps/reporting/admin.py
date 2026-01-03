from django.contrib import admin
from .models import ShiftReport


@admin.register(ShiftReport)
class ShiftReportAdmin(admin.ModelAdmin):
    list_display = ('shift_plan', 'created_at')
