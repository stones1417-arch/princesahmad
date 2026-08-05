from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.dashboard.models import SystemActivityLog


@login_required
def system_center_view(request: HttpRequest) -> HttpResponse:
    """Institutional entry point for platform governance and administration."""
    if not request.user.is_superuser:
        raise PermissionDenied("هذه الصفحة متاحة لمدير النظام فقط.")

    User = get_user_model()
    today = timezone.localdate()
    registered_models = sum(
        1 for model in apps.get_models() if not model._meta.auto_created
    )

    recent_activity = (
        SystemActivityLog.objects.select_related("user")
        .order_by("-created_at")[:6]
    )

    context = {
        "active_users": User.objects.filter(is_active=True).count(),
        "staff_users": User.objects.filter(is_staff=True, is_active=True).count(),
        "groups_count": Group.objects.count(),
        "registered_models": registered_models,
        "today_activity": SystemActivityLog.objects.filter(
            created_at__date=today
        ).count(),
        "recent_activity": recent_activity,
        "database_vendor": connection.vendor,
        "system_time": timezone.localtime(),
    }
    return render(request, "dashboard/system_center.html", context)
