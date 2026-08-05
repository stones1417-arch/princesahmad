from django.contrib import admin

from .models import ExportLog


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    list_display = (
        "module",
        "user",
        "export_format",
        "status",
        "records_count",
        "formatted_size",
        "download_count",
        "created_at",
    )
    list_filter = (
        "export_format",
        "status",
        "module",
        "created_at",
    )
    search_fields = (
        "module",
        "file_name",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    readonly_fields = (
        "user",
        "module",
        "report_key",
        "file_name",
        "file",
        "export_format",
        "status",
        "records_count",
        "file_size",
        "filters",
        "error_message",
        "requested_ip",
        "user_agent",
        "download_count",
        "last_downloaded_at",
        "created_at",
        "completed_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="حجم الملف")
    def formatted_size(self, obj):
        return obj.formatted_file_size
