from django.contrib import admin

from .models import Break


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "shift_type",
        "job_title",
        "rest_days",
        "is_active",
        "created_at",
    )

    list_filter = (
        "shift_type",
        "job_title",
        "rest_days",
        "is_active",
    )

    search_fields = (
        "employee__full_name",
        "employee__employee_number",
        "employee__phone_number",
        "notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "shift_type__name",
        "rest_days",
        "employee__employee_number",
    )