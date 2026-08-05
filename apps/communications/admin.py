from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "priority",
        "is_active",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "priority",
        "is_active",
        "created_at",
    ]

    search_fields = [
        "title",
        "content",
        "created_by__username",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    ordering = [
        "-created_at",
    ]