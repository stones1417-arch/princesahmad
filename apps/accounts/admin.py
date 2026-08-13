from django.contrib import admin
from django.db.models import Case, IntegerField, Value, When

from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions

from .models import AccountRegistrationRequest, Role, TwoFactorAuditLog, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)


@admin.register(AccountRegistrationRequest)
class AccountRegistrationRequestAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "employee_number",
        "requested_username",
        "email",
        "phone_number",
        "gender",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("status", "gender", "created_at", "reviewed_at")
    search_fields = (
        "full_name",
        "employee_number",
        "requested_username",
        "email",
        "phone_number",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "created_user",
        "linked_employee",
        "reviewed_at",
    )
    ordering = ("-created_at",)

    def has_module_permission(self, request):
        return bool(
            request.user.is_authenticated
            and request.user.is_staff
            and user_has_permission(request.user, PlatformPermissions.MANAGE_USERS)
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            status_priority=Case(
                When(status=AccountRegistrationRequest.Status.PENDING, then=Value(0)),
                When(status=AccountRegistrationRequest.Status.NEEDS_EDIT, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("status_priority", "-created_at")


@admin.register(TwoFactorAuditLog)
class TwoFactorAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "channel", "status", "ip_address", "created_at")
    list_filter = ("event", "channel", "status")
    search_fields = ("user__username",)
    readonly_fields = tuple(field.name for field in TwoFactorAuditLog._meta.fields)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"}

    def has_delete_permission(self, request, obj=None):
        return False
