from django.contrib import admin
from django.contrib.auth.models import Group

from .models import Role, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "is_system_role",
        "is_active",
        "permissions_count",
        "updated_at",
    ]

    list_filter = [
        "is_system_role",
        "is_active",
    ]

    search_fields = [
        "name",
        "code",
        "description",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "بيانات الدور",
            {
                "fields": [
                    "code",
                    "name",
                    "description",
                    "group",
                ],
            },
        ),
        (
            "الحالة",
            {
                "fields": [
                    "is_system_role",
                    "is_active",
                ],
            },
        ),
        (
            "التواريخ",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
            },
        ),
    ]

    def permissions_count(self, obj):
        return obj.group.permissions.count()

    permissions_count.short_description = (
        "عدد الصلاحيات"
    )


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "role",
        "is_active",
        "assigned_by",
        "assigned_at",
    ]

    list_filter = [
        "is_active",
        "role",
    ]

    search_fields = [
        "user__username",
        "user__first_name",
        "user__last_name",
        "role__name",
        "role__code",
    ]

    autocomplete_fields = [
        "user",
        "assigned_by",
    ]

    readonly_fields = [
        "assigned_at",
        "updated_at",
    ]

    list_select_related = [
        "user",
        "role",
        "assigned_by",
    ]


# إخفاء Group من لوحة الإدارة لأن إدارته ستكون من خلال Role.
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass