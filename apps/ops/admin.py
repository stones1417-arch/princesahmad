from django.contrib import admin

from .models import (
    DoorShift,
    MaintenanceRequest,
    Incident,
)


@admin.register(DoorShift)
class DoorShiftAdmin(admin.ModelAdmin):
    list_display = (
        "door_number",
        "shift_plan",
        "state",
        "supervisor",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "state",
        "is_active",
        "shift_plan",
    )

    search_fields = (
        "door_number",
    )

    ordering = (
        "door_number",
    )


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_number",
        "door_shift",
        "priority",
        "status",
        "technician_name",
        "created_by",
        "created_at",
    )

    list_filter = (
        "priority",
        "status",
        "created_at",
    )

    search_fields = (
        "request_number",
        "door_shift__door_number",
        "description",
        "technician_name",
    )

    readonly_fields = (
        "request_number",
        "created_at",
        "approved_at",
        "assigned_at",
        "started_at",
        "fixed_at",
        "closed_at",
    )

    ordering = (
        "-created_at",
    )


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "incident_number",
        "incident_type",
        "priority",
        "status",
        "door_shift",
        "reported_by_name",
        "assigned_to_name",
        "created_at",
    )

    list_filter = (
        "incident_type",
        "priority",
        "status",
        "created_at",
    )

    search_fields = (
        "incident_number",
        "description",
        "reported_by_name",
        "assigned_to_name",
    )

    readonly_fields = (
        "incident_number",
        "created_at",
        "updated_at",
        "closed_at",
    )

    ordering = (
        "-created_at",
    )

    fieldsets = (
        (
            "بيانات البلاغ",
            {
                "fields": (
                    "incident_number",
                    "incident_type",
                    "priority",
                    "status",
                )
            },
        ),

        (
            "الربط التشغيلي",
            {
                "fields": (
                    "shift_plan",
                    "door_shift",
                )
            },
        ),

        (
            "تفاصيل البلاغ",
            {
                "fields": (
                    "description",
                    "reported_by_name",
                    "assigned_to_name",
                )
            },
        ),

        (
            "الإغلاق",
            {
                "fields": (
                    "closing_notes",
                    "closed_by",
                    "closed_at",
                )
            },
        ),

        (
            "التدقيق",
            {
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )