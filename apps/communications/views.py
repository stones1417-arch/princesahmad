from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_date

from apps.core.notification_service import NotificationService
from apps.core.permissions import require_staff
from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog
from apps.roles.services.section_access import (
    get_allowed_sections,
    has_institutional_scope,
)
from apps.roles.services.section_context import (
    get_effective_section,
)

from io import StringIO

from .forms import AnnouncementForm
from .models import (
    Announcement,
    CommunicationLog,
)
from .services.assignment_message_service import (
    build_assignment_message,
    retry_assignment_message,
)


# ============================================================
# Communications Access Helpers
# ============================================================


def _communication_logs_visible_to_user(
    user,
    queryset: QuerySet | None = None,
) -> QuerySet:
    """
    إرجاع سجلات الاتصالات التي يحق للمستخدم رؤيتها.

    القواعد:
    - المستخدم غير المسجل لا يرى شيئًا.
    - superuser يرى جميع السجلات.
    - المستخدم ذو النطاق المؤسسي يرى جميع السجلات.
    - بقية المستخدمين يرون السجلات الخاصة بالأقسام
      المسموح لهم بها، بالإضافة إلى السجلات العامة.
    - يتم استخدام نظام section_access المركزي
      بدل استنتاج القسم من الجنس مباشرة.

    يمكن تمرير QuerySet مخصص، أو سيتم استخدام
    جميع سجلات CommunicationLog افتراضيًا.
    """

    user = getattr(user, "user", user)
    if queryset is None:
        queryset = CommunicationLog.objects.all()

    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return queryset.none()

    if getattr(
        user,
        "is_superuser",
        False,
    ):
        return queryset

    allowed_sections = {
        str(section).strip().lower()
        for section in get_allowed_sections(user)
        if str(section).strip()
    }

    if not allowed_sections:
        return queryset.none()

    return queryset.filter(
        Q(section="all")
        | Q(section__in=allowed_sections)
    )


CURRENT_COMMUNICATION_CHANNELS = {"sms", "whatsapp", "email"}


def _filtered_communication_logs(request, queryset):
    channel = (request.GET.get("channel") or "").strip().lower()
    status = (request.GET.get("status") or "").strip().lower()
    section = (request.GET.get("section") or "").strip().lower()
    message_type = (request.GET.get("type") or "").strip().lower()
    if channel in CURRENT_COMMUNICATION_CHANNELS:
        queryset = queryset.filter(channel=channel)
    if status in CommunicationLog.Status.values:
        queryset = queryset.filter(status=status)
    if section in {"male", "female"}:
        queryset = queryset.filter(section=section)
    if message_type == "assignment":
        queryset = queryset.filter(related_assignment__isnull=False)
    return queryset


@login_required
def communications_dashboard_view(request):
    require_staff(request.user)
    logs = _filtered_communication_logs(
        request,
        _communication_logs_visible_to_user(request.user).order_by("-created_at"),
    )
    page = Paginator(logs, 25).get_page(request.GET.get("page"))
    return render(request, "communications/dashboard.html", {
        "communication_page": page,
        "channel_choices": [
            choice for choice in CommunicationLog.Channel.choices
            if choice[0] in CURRENT_COMMUNICATION_CHANNELS
        ],
        "status_choices": CommunicationLog.Status.choices,
    })


@login_required
def communication_logs_view(request):
    require_staff(request.user)
    logs = _filtered_communication_logs(
        request,
        _communication_logs_visible_to_user(request.user).order_by("-created_at"),
    )
    page = Paginator(logs, 50).get_page(request.GET.get("page"))
    return render(request, "communications/logs.html", {
        "page_obj": page,
        "channel_choices": [
            choice for choice in CommunicationLog.Channel.choices
            if choice[0] in CURRENT_COMMUNICATION_CHANNELS
        ],
        "status_choices": CommunicationLog.Status.choices,
    })


@login_required
def communication_log_detail_view(request, pk):
    require_staff(request.user)
    log = get_object_or_404(_communication_logs_visible_to_user(request.user), pk=pk)
    may_view_errors = request.user.is_superuser or request.user.has_perm(
        "communications.can_view_communication_errors"
    )
    return render(request, "communications/detail.html", {
        "log": log,
        "may_view_errors": may_view_errors,
    })


def _assignment_message_logs(request):
    queryset = (
        _communication_logs_visible_to_user(request.user)
        .filter(related_assignment__isnull=False)
        .select_related(
            "recipient_employee",
            "recipient_user",
            "related_assignment",
            "related_door",
            "related_shift__shift_type",
            "provider",
        )
    )
    query = (request.GET.get("q") or "").strip()
    channel = (request.GET.get("channel") or "").strip().lower()
    status = (request.GET.get("status") or "").strip().lower()
    section = (request.GET.get("section") or "").strip().lower()
    door = (request.GET.get("door") or "").strip()
    shift = (request.GET.get("shift") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(recipient_employee__full_name__icontains=query)
            | Q(recipient_employee__employee_number__icontains=query)
            | Q(recipient_user__username__icontains=query)
            | Q(related_door__door_number__icontains=query)
            | Q(related_shift__shift_type__name__icontains=query)
        )
    if channel in {"sms", "whatsapp"}:
        queryset = queryset.filter(channel=channel)
    if status in {
        CommunicationLog.Status.PENDING,
        CommunicationLog.Status.SENT,
        CommunicationLog.Status.FAILED,
        CommunicationLog.Status.SKIPPED,
    }:
        queryset = queryset.filter(status=status)
    if section in {"male", "female"}:
        queryset = queryset.filter(section=section)
    if door.isdigit():
        queryset = queryset.filter(related_door_id=int(door))
    if shift.isdigit():
        queryset = queryset.filter(related_shift_id=int(shift))
    parsed_date_from = parse_date(date_from) if date_from else None
    parsed_date_to = parse_date(date_to) if date_to else None
    if parsed_date_from:
        queryset = queryset.filter(created_at__date__gte=parsed_date_from)
    if parsed_date_to:
        queryset = queryset.filter(created_at__date__lte=parsed_date_to)
    return queryset


def _safe_assignment_error(log):
    if log.error_code == "invalid_recipient":
        return "رقم جوال الموظف غير صالح أو غير مسجل."
    if log.error_code == "operational_messaging_not_configured":
        return "الإرسال التشغيلي الخارجي غير مفعّل حاليًا."
    if log.status == CommunicationLog.Status.SKIPPED:
        return "تم تخطي الرسالة بسبب بيانات المستلم."
    if log.status == CommunicationLog.Status.FAILED:
        return "تعذر إرسال الرسالة."
    return ""


@login_required
def assignment_messages_view(request):
    require_staff(request.user)
    logs = _assignment_message_logs(request)
    stats = logs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=CommunicationLog.Status.PENDING)),
        sent=Count("id", filter=Q(status=CommunicationLog.Status.SENT)),
        failed=Count("id", filter=Q(status=CommunicationLog.Status.FAILED)),
        skipped=Count("id", filter=Q(status=CommunicationLog.Status.SKIPPED)),
        sms=Count("id", filter=Q(channel=CommunicationLog.Channel.SMS)),
        whatsapp=Count("id", filter=Q(channel=CommunicationLog.Channel.WHATSAPP)),
    )
    page = Paginator(logs.order_by("-created_at"), 50).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "communications/assignment_messages.html", {
        "page_obj": page,
        "stats": stats,
        "query_string": params.urlencode(),
        "channel_choices": (("sms", "SMS"), ("whatsapp", "WhatsApp")),
        "status_choices": (
            (CommunicationLog.Status.PENDING, "انتظار"),
            (CommunicationLog.Status.SENT, "تم الإرسال"),
            (CommunicationLog.Status.FAILED, "فشل"),
            (CommunicationLog.Status.SKIPPED, "تم التخطي"),
        ),
    })


@login_required
def assignment_message_detail_view(request, pk):
    require_staff(request.user)
    log = get_object_or_404(_assignment_message_logs(request), pk=pk)
    message_snapshot = log.message_body or build_assignment_message(log.related_assignment)
    return render(request, "communications/assignment_message_detail.html", {
        "log": log,
        "message_snapshot": message_snapshot,
        "safe_error": _safe_assignment_error(log),
        "may_retry": request.user.is_superuser or request.user.has_perm(
            "communications.can_retry_assignment_message"
        ),
    })


@login_required
@require_POST
def assignment_message_retry_view(request, pk):
    require_staff(request.user)
    if not (request.user.is_superuser or request.user.has_perm("communications.can_retry_assignment_message")):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("لا تملك صلاحية إعادة محاولة رسائل التكليف.")
    log = get_object_or_404(_assignment_message_logs(request), pk=pk)
    try:
        retry_assignment_message(log)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "الإرسال التشغيلي الخارجي غير مفعّل حاليًا. تم الاحتفاظ بالرسالة بحالة الانتظار.")
    return redirect("communications:assignment-message-detail", pk=log.pk)


@login_required
def authentica_provider_view(request):
    require_staff(request.user)
    check_output = ""
    if request.method == "POST":
        output = StringIO()
        call_command("authentica_config_check", stdout=output)
        check_output = output.getvalue()
    configured = "Configured" if settings.AUTHENTICA_API_KEY else "Missing"
    current_release_services = [
        {"name": name, "status": configured, "sender_status": "-"}
        for name in ("SMS", "WhatsApp", "Email", "OTP")
    ]
    future_services = [
        {"name": name, "status": "غير مفعلة - تتطلب موافقة وإعداد رسمي"}
        for name in ("Voice", "Face", "Nafath")
    ]
    return render(request, "communications/provider.html", {
        "api_key_status": configured,
        "current_release_services": current_release_services,
        "future_services": future_services,
        "check_output": check_output,
    })


def authentica_webhook_view(request):
    return JsonResponse({"status": "NOT_CONFIGURED"}, status=503)


def _announcements_visible_to_user(
    request,
) -> QuerySet:
    """
    إرجاع التعاميم التي يحق للمستخدم رؤيتها
    وفق نطاق القسم التشغيلي.
    """

    announcements = (
        Announcement.objects
        .select_related(
            "created_by"
        )
    )

    if getattr(
        request.user,
        "is_superuser",
        False,
    ):
        return announcements

    if has_institutional_scope(
        request.user
    ):
        return announcements

    allowed_sections = {
        str(section).strip().lower()
        for section in get_allowed_sections(
            request.user
        )
        if str(section).strip()
    }

    if not allowed_sections:
        return announcements.none()

    return announcements.filter(
        Q(
            section=(
                Announcement
                .OperationalSection
                .ALL
            )
        )
        | Q(
            section__in=allowed_sections
        )
    )


# ============================================================
# Announcement List
# ============================================================


@login_required
def announcement_list_view(
    request,
):
    """
    سجل التعاميم الإدارية مع:
    - البحث
    - التصفية
    - القسم التشغيلي
    - الإحصائيات
    """

    require_staff(
        request.user
    )

    query = (
        request.GET.get(
            "q"
        )
        or ""
    ).strip()

    priority = (
        request.GET.get(
            "priority"
        )
        or ""
    ).strip()

    status = (
        request.GET.get(
            "status"
        )
        or ""
    ).strip()

    announcements = (
        _announcements_visible_to_user(
            request
        )
        .order_by(
            "-created_at"
        )
    )

    # --------------------------------------------------------
    # Operational Section
    # --------------------------------------------------------

    selected_section = (
        get_effective_section(
            request
        )
    )

    if (
        selected_section
        != Announcement
        .OperationalSection
        .ALL
    ):
        announcements = (
            announcements.filter(
                section__in=[
                    (
                        Announcement
                        .OperationalSection
                        .ALL
                    ),
                    selected_section,
                ]
            )
        )

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    if query:
        announcements = (
            announcements.filter(
                Q(
                    title__icontains=query
                )
                | Q(
                    content__icontains=query
                )
                | Q(
                    created_by__username__icontains=query
                )
                | Q(
                    created_by__first_name__icontains=query
                )
                | Q(
                    created_by__last_name__icontains=query
                )
            )
        )

    # --------------------------------------------------------
    # Priority
    # --------------------------------------------------------

    if priority:
        announcements = (
            announcements.filter(
                priority=priority
            )
        )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if status == "active":
        announcements = (
            announcements.filter(
                is_active=True
            )
        )

    elif status == "inactive":
        announcements = (
            announcements.filter(
                is_active=False
            )
        )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    all_announcements = (
        _announcements_visible_to_user(
            request
        )
    )

    context = {
        "announcements": announcements,

        "announcements_count": (
            announcements.count()
        ),

        "total_announcements": (
            all_announcements.count()
        ),

        "active_announcements": (
            all_announcements.filter(
                is_active=True
            ).count()
        ),

        "inactive_announcements": (
            all_announcements.filter(
                is_active=False
            ).count()
        ),

        "urgent_announcements": (
            all_announcements.filter(
                priority=(
                    Announcement
                    .Priority
                    .URGENT
                )
            ).count()
        ),

        "priority_choices": (
            Announcement
            .Priority
            .choices
        ),

        "q": query,

        "selected_priority": (
            priority
        ),

        "selected_status": (
            status
        ),

        "selected_operational_section": (
            selected_section
        ),
    }

    return render(
        request,
        (
            "communications/"
            "announcement_list.html"
        ),
        context,
    )


# ============================================================
# Announcement Detail
# ============================================================


@login_required
def announcement_detail_view(
    request,
    pk,
):
    """
    عرض تفاصيل تعميم إداري واحد.

    يستخدم QuerySet المفلتر حسب صلاحيات القسم
    لمنع الوصول المباشر إلى تعميم من قسم آخر.
    """

    require_staff(
        request.user
    )

    announcement = (
        get_object_or_404(
            _announcements_visible_to_user(
                request
            ),
            pk=pk,
        )
    )

    return render(
        request,
        (
            "communications/"
            "announcement_detail.html"
        ),
        {
            "announcement": (
                announcement
            ),
        },
    )


# ============================================================
# Announcement Create
# ============================================================


@login_required
def announcement_create_view(
    request,
):
    """
    إنشاء تعميم إداري جديد.
    """

    require_staff(
        request.user
    )

    if request.method == "POST":
        form = AnnouncementForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            announcement = (
                form.save(
                    commit=False
                )
            )

            announcement.created_by = (
                request.user
            )

            announcement.save()

            # ------------------------------------------------
            # Activity Log
            # ------------------------------------------------

            log_activity(
                user=request.user,
                module=(
                    "التعاميم الإدارية"
                ),
                action=(
                    SystemActivityLog
                    .ActionType
                    .CREATE
                ),
                description=(
                    "تم إنشاء التعميم الإداري: "
                    f"{announcement.title}"
                ),
                request=request,
            )

            # ------------------------------------------------
            # Notification
            # ------------------------------------------------

            NotificationService.success(
                title=(
                    "تعميم إداري جديد"
                ),
                message=(
                    "القسم: "
                    f"{announcement.get_section_display()}"
                    " | التعميم: "
                    f"{announcement.title}"
                ),
                users=(
                    get_user_model()
                    .objects
                    .filter(
                        is_active=True
                    )
                ),
                url="/communications/",
                section=(
                    announcement.section
                ),
            )

            messages.success(
                request,
                (
                    "تم إنشاء التعميم "
                    "الإداري بنجاح."
                ),
            )

            return redirect(
                "communications:list"
            )

    else:
        form = AnnouncementForm()

    return render(
        request,
        (
            "communications/"
            "announcement_form.html"
        ),
        {
            "form": form,
            "page_title": (
                "إضافة تعميم إداري"
            ),
            "submit_text": (
                "حفظ التعميم"
            ),
        },
    )


# ============================================================
# Announcement Update
# ============================================================


@login_required
def announcement_update_view(
    request,
    pk,
):
    """
    تعديل تعميم إداري.

    يتم جلب التعميم من النطاق المسموح للمستخدم
    وليس من جميع التعاميم.
    """

    require_staff(
        request.user
    )

    announcement = (
        get_object_or_404(
            _announcements_visible_to_user(
                request
            ),
            pk=pk,
        )
    )

    if request.method == "POST":
        form = AnnouncementForm(
            request.POST,
            request.FILES,
            instance=announcement,
        )

        if form.is_valid():
            announcement = (
                form.save()
            )

            # ------------------------------------------------
            # Activity Log
            # ------------------------------------------------

            log_activity(
                user=request.user,
                module=(
                    "التعاميم الإدارية"
                ),
                action=(
                    SystemActivityLog
                    .ActionType
                    .UPDATE
                ),
                description=(
                    "تم تعديل التعميم الإداري: "
                    f"{announcement.title}"
                ),
                request=request,
            )

            # ------------------------------------------------
            # Notification
            # ------------------------------------------------

            NotificationService.info(
                title=(
                    "تم تعديل تعميم إداري"
                ),
                message=(
                    "تم تعديل التعميم: "
                    f"{announcement.title}"
                ),
                user=request.user,
                url="/communications/",
            )

            messages.success(
                request,
                (
                    "تم تعديل التعميم "
                    "الإداري بنجاح."
                ),
            )

            return redirect(
                "communications:list"
            )

    else:
        form = AnnouncementForm(
            instance=announcement,
        )

    return render(
        request,
        (
            "communications/"
            "announcement_form.html"
        ),
        {
            "form": form,
            "announcement": (
                announcement
            ),
            "page_title": (
                "تعديل التعميم الإداري"
            ),
            "submit_text": (
                "حفظ التعديلات"
            ),
        },
    )


# ============================================================
# Announcement Toggle Status
# ============================================================


@login_required
def announcement_toggle_status_view(
    request,
    pk,
):
    """
    تفعيل أو تعطيل تعميم إداري.
    """

    require_staff(
        request.user
    )

    announcement = (
        get_object_or_404(
            _announcements_visible_to_user(
                request
            ),
            pk=pk,
        )
    )

    if request.method != "POST":
        return redirect(
            "communications:list"
        )

    announcement.is_active = (
        not announcement.is_active
    )

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

    # --------------------------------------------------------
    # Activity Log
    # --------------------------------------------------------

    log_activity(
        user=request.user,
        module=(
            "التعاميم الإدارية"
        ),
        action=(
            SystemActivityLog
            .ActionType
            .UPDATE
        ),
        description=(
            f"تم {action_text} "
            "التعميم الإداري: "
            f"{announcement.title}"
        ),
        request=request,
    )

    # --------------------------------------------------------
    # Notification
    # --------------------------------------------------------

    NotificationService.warning(
        title=(
            f"تم {action_text} "
            "تعميم إداري"
        ),
        message=(
            f"تم {action_text} التعميم: "
            f"{announcement.title}"
        ),
        user=request.user,
        url="/communications/",
    )

    messages.success(
        request,
        (
            f"تم {action_text} "
            "التعميم بنجاح."
        ),
    )

    return redirect(
        "communications:list"
    )


# ============================================================
# Announcement Delete
# ============================================================


@login_required
def announcement_delete_view(
    request,
    pk,
):
    """
    حذف تعميم إداري بعد صفحة التأكيد.

    يتم تطبيق نطاق القسم قبل السماح بالحذف.
    """

    require_staff(
        request.user
    )

    announcement = (
        get_object_or_404(
            _announcements_visible_to_user(
                request
            ),
            pk=pk,
        )
    )

    if request.method == "POST":
        announcement_title = (
            announcement.title
        )

        # ----------------------------------------------------
        # Activity Log
        # ----------------------------------------------------

        log_activity(
            user=request.user,
            module=(
                "التعاميم الإدارية"
            ),
            action=(
                SystemActivityLog
                .ActionType
                .DELETE
            ),
            description=(
                "تم حذف التعميم الإداري: "
                f"{announcement_title}"
            ),
            request=request,
        )

        announcement.delete()

        # ----------------------------------------------------
        # Notification
        # ----------------------------------------------------

        NotificationService.danger(
            title=(
                "تم حذف تعميم إداري"
            ),
            message=(
                "تم حذف التعميم: "
                f"{announcement_title}"
            ),
            user=request.user,
            url="/communications/",
        )

        messages.success(
            request,
            (
                "تم حذف التعميم "
                "الإداري بنجاح."
            ),
        )

        return redirect(
            "communications:list"
        )

    return render(
        request,
        (
            "communications/"
            "announcement_confirm_delete.html"
        ),
        {
            "announcement": (
                announcement
            ),
        },
    )