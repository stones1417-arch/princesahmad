from django.contrib import admin

from .models import SystemConfiguration


@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    """Break-glass access; routine configuration belongs to the platform UI."""

    readonly_fields = ("updated_at",)
