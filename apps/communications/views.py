from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.notification_service import NotificationService
from apps.core.permissions import require_staff
from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog

from .forms import AnnouncementForm
from .models import Announcement


@login_required
def announcement_list_view(request):
    """
    سجل التعاميم الإدارية مع البحث والتصفية والإحصائيات.
    """
    require_staff(request.user)

    query = (request.GET.get("q") or "").strip()
    priority = (request.GET.get("priority") or "").strip()
    status = (request.GET.get("status") or "").strip()

    announcements = (
        Announcement.objects
        .select_related("created_by")
        .order_by("-created_at")
    )

    if query:
        announcements = announcements.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(created_by__username__icontains=query)
            | Q(created_by__first_name__icontains=query)
            | Q(created_by__last_name__icontains=query)
        )

    if priority:
        announcements = announcements.filter(priority=priority)

    if status == "active":
        announcements = announcements.filter(is_active=True)

    elif status == "inactive":
        announcements = announcements.filter(is_active=False)

    all_announcements = Announcement.objects.all()

    context = {
        "announcements": announcements,
        "announcements_count": announcements.count(),
        "total_announcements": all_announcements.count(),
        "active_announcements": all_announcements.filter(
            is_active=True
        ).count(),
        "inactive_announcements": all_announcements.filter(
            is_active=False
        ).count(),
        "urgent_announcements": all_announcements.filter(
            priority=Announcement.Priority.URGENT
        ).count(),
        "priority_choices": Announcement.Priority.choices,
        "q": query,
        "selected_priority": priority,
        "selected_status": status,
    }

    return render(
        request,
        "communications/announcement_list.html",
        context,
    )


@login_required
def announcement_detail_view(request, pk):
    """
    عرض تفاصيل تعميم إداري واحد.
    """
    require_staff(request.user)

    announcement = get_object_or_404(
        Announcement.objects.select_related("created_by"),
        pk=pk,
    )

    return render(
        request,
        "communications/announcement_detail.html",
        {
            "announcement": announcement,
        },
    )


@login_required
def announcement_create_view(request):
    """
    إنشاء تعميم إداري جديد.
    """
    require_staff(request.user)

    if request.method == "POST":
        form = AnnouncementForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            announcement.save()

            log_activity(
                user=request.user,
                module="التعاميم الإدارية",
                action=SystemActivityLog.ActionType.CREATE,
                description=(
                    f"تم إنشاء التعميم الإداري: "
                    f"{announcement.title}"
                ),
                request=request,
            )

            NotificationService.success(
                title="تم إنشاء تعميم إداري",
                message=f"تم إنشاء التعميم: {announcement.title}",
                user=request.user,
                url="/communications/",
            )

            messages.success(
                request,
                "تم إنشاء التعميم الإداري بنجاح.",
            )

            return redirect("communications:list")

    else:
        form = AnnouncementForm()

    return render(
        request,
        "communications/announcement_form.html",
        {
            "form": form,
            "page_title": "إضافة تعميم إداري",
            "submit_text": "حفظ التعميم",
        },
    )


@login_required
def announcement_update_view(request, pk):
    """
    تعديل تعميم إداري.
    """
    require_staff(request.user)

    announcement = get_object_or_404(
        Announcement,
        pk=pk,
    )

    if request.method == "POST":
        form = AnnouncementForm(
            request.POST,
            request.FILES,
            instance=announcement,
        )

        if form.is_valid():
            announcement = form.save()

            log_activity(
                user=request.user,
                module="التعاميم الإدارية",
                action=SystemActivityLog.ActionType.UPDATE,
                description=(
                    f"تم تعديل التعميم الإداري: "
                    f"{announcement.title}"
                ),
                request=request,
            )

            NotificationService.info(
                title="تم تعديل تعميم إداري",
                message=f"تم تعديل التعميم: {announcement.title}",
                user=request.user,
                url="/communications/",
            )

            messages.success(
                request,
                "تم تعديل التعميم الإداري بنجاح.",
            )

            return redirect("communications:list")

    else:
        form = AnnouncementForm(
            instance=announcement,
        )

    return render(
        request,
        "communications/announcement_form.html",
        {
            "form": form,
            "announcement": announcement,
            "page_title": "تعديل التعميم الإداري",
            "submit_text": "حفظ التعديلات",
        },
    )


@login_required
def announcement_toggle_status_view(request, pk):
    """
    تفعيل أو تعطيل تعميم إداري.
    """
    require_staff(request.user)

    announcement = get_object_or_404(
        Announcement,
        pk=pk,
    )

    if request.method != "POST":
        return redirect("communications:list")

    announcement.is_active = not announcement.is_active
    announcement.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    action_text = (
        "تفعيل"
        if announcement.is_active
        else "تعطيل"
    )

    log_activity(
        user=request.user,
        module="التعاميم الإدارية",
        action=SystemActivityLog.ActionType.UPDATE,
        description=(
            f"تم {action_text} التعميم الإداري: "
            f"{announcement.title}"
        ),
        request=request,
    )

    NotificationService.warning(
        title=f"تم {action_text} تعميم إداري",
        message=(
            f"تم {action_text} التعميم: "
            f"{announcement.title}"
        ),
        user=request.user,
        url="/communications/",
    )

    messages.success(
        request,
        f"تم {action_text} التعميم بنجاح.",
    )

    return redirect("communications:list")


@login_required
def announcement_delete_view(request, pk):
    """
    حذف تعميم إداري بعد صفحة تأكيد.
    """
    require_staff(request.user)

    announcement = get_object_or_404(
        Announcement,
        pk=pk,
    )

    if request.method == "POST":
        announcement_title = announcement.title

        log_activity(
            user=request.user,
            module="التعاميم الإدارية",
            action=SystemActivityLog.ActionType.DELETE,
            description=(
                f"تم حذف التعميم الإداري: "
                f"{announcement_title}"
            ),
            request=request,
        )

        announcement.delete()

        NotificationService.danger(
            title="تم حذف تعميم إداري",
            message=f"تم حذف التعميم: {announcement_title}",
            user=request.user,
            url="/communications/",
        )

        messages.success(
            request,
            "تم حذف التعميم الإداري بنجاح.",
        )

        return redirect("communications:list")

    return render(
        request,
        "communications/announcement_confirm_delete.html",
        {
            "announcement": announcement,
        },
    )