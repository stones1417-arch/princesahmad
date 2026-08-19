from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.dashboard.models import SystemActivityLog
from apps.locations.models import Door
from apps.roles.models import Role
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.decorators import permission_required
from apps.scheduling.models import ShiftType

from .forms import SystemConfigurationForm
from .system_settings import (
    ConcurrentSettingsUpdate,
    SystemHealthService,
    SystemSettingsService,
)
from apps.roles.services.section_context import set_current_section


@login_required
@require_POST
def set_operational_section(request):
    """Persist the platform-wide operational section selected from the header."""
    set_current_section(request, request.POST.get("section"))

    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("dashboard:index")


@login_required
@permission_required(PlatformPermissions.VIEW_SYSTEM_SETTINGS)
def system_settings_view(request):
    configuration = SystemSettingsService.get_settings()
    can_change = user_has_permission(
        request.user, PlatformPermissions.CHANGE_SYSTEM_SETTINGS
    )

    if request.method == "POST":
        if not can_change:
            raise PermissionDenied("ليس لديك صلاحية تعديل إعدادات النظام.")
        form = SystemConfigurationForm(request.POST, instance=configuration)
        if form.is_valid():
            try:
                configuration = SystemSettingsService.update_settings(
                    values=form.cleaned_data,
                    request=request,
                    expected_updated_at=form.cleaned_data["updated_at"],
                )
            except ConcurrentSettingsUpdate as error:
                form.add_error(None, error.message)
            else:
                messages.success(request, "تم حفظ إعدادات النظام بنجاح")
                return redirect("core:system-settings")
    else:
        form = SystemConfigurationForm(instance=configuration)

    if not can_change:
        for field_name, field in form.fields.items():
            if field_name != "updated_at":
                field.disabled = True

    environment = {
        "database": bool(settings.DATABASES["default"].get("ENGINE")),
        "redis": bool(getattr(settings, "REDIS_URL", "")),
        "cloudinary": all(
            getattr(settings, name, "")
            for name in (
                "CLOUDINARY_CLOUD_NAME",
                "CLOUDINARY_API_KEY",
                "CLOUDINARY_API_SECRET",
            )
        ),
        "smtp": bool(settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL),
        "sms_credentials": bool(
            getattr(settings, "FOURJAWALY_API_KEY", "")
            and getattr(settings, "FOURJAWALY_API_SECRET", "")
        ),
        "sms_sender": bool(getattr(settings, "FOURJAWALY_SENDER_ID", "")),
        "celery": bool(getattr(settings, "CELERY_BROKER_URL", "")),
    }
    security = {
        "debug_disabled": not settings.DEBUG,
        "https_redirect": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "secure_session": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "secure_csrf": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "hsts_enabled": bool(getattr(settings, "SECURE_HSTS_SECONDS", 0)),
        "allowed_hosts_configured": bool(settings.ALLOWED_HOSTS),
    }
    metrics = {
        "active_doors": Door.objects.filter(is_active=True).count(),
        "shift_types": ShiftType.objects.count(),
        "operational_sections": len(Role.OperationalSection.choices),
        "duplicate_doors": (
            Door.objects.values("door_number")
            .annotate(total=Count("pk"))
            .filter(total__gt=1)
            .count()
        ),
    }
    history = (
        SystemActivityLog.objects.filter(module="إعدادات النظام")
        .select_related("user")[:10]
    )
    return render(
        request,
        "core/system_settings.html",
        {
            "form": form,
            "configuration": configuration,
            "can_change": can_change,
            "environment": environment,
            "security": security,
            "metrics": metrics,
            "service_statuses": SystemHealthService.collect(),
            "history": history,
            "default_from_email": settings.DEFAULT_FROM_EMAIL,
            "sms_provider": getattr(settings, "SMS_PROVIDER", "4jawaly"),
        },
    )
