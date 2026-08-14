from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.notification_service import NotificationService
from apps.communications.models import CommunicationLog
from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.roles.services.section_access import (
    can_manage_section,
    filter_assignments_for_user,
    filter_doors_for_user,
    filter_employees_for_user,
    get_allowed_sections,
    has_institutional_scope,
)
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.scheduling.models import ShiftAssignment, ShiftPlan
from apps.audit.models import AssignmentHistory

from .models import DoorAssignment
from .services import DistributionService


def _available_doors_queryset():
    return DistributionService.operational_doors()


def _door_display_name(door: Door) -> str:
    return f"باب {door.door_number}" if door.door_number is not None else (door.name or "باب غير محدد")


def _active_shift():
    return (
        ShiftPlan.objects.select_related("shift_type")
        .filter(is_active=True)
        .first()
    )


def _can_manage_assignment_section(user, section: str) -> bool:
    return user.is_superuser or (
        has_institutional_scope(user)
        and can_manage_section(user, section)
    )


def _require_distribution_permission(request, permission):
    if request.user.is_superuser:
        return
    if (
        not user_has_permission(request.user, permission)
        or not has_institutional_scope(request.user)
    ):
        raise PermissionDenied("لا تملك صلاحية الوصول إلى التوزيع.")


def _require_all_sections(request):
    _require_distribution_permission(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    if not request.user.is_superuser and get_allowed_sections(request.user) != {"male", "female"}:
        raise PermissionDenied("تتطلب العملية نطاق الأقسام كافة.")


@login_required
def distribution_dashboard_view(request):
    _require_distribution_permission(request, PlatformPermissions.VIEW_DISTRIBUTION)
    active_shift = _active_shift()
    doors = _available_doors_queryset()

    scoped_user = has_institutional_scope(request.user)
    allowed_sections = get_allowed_sections(request.user)
    has_all_sections = (
        not scoped_user
        or "all" in allowed_sections
    )

    assignments = DoorAssignment.objects.none()
    available_employees = Employee.objects.none()
    report = None

    query = (request.GET.get("q") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    door_filter = (request.GET.get("door") or "").strip()
    operational_section_filter = (
        request.GET.get("operational_section") or ""
    ).strip()

    if active_shift:
        doors = doors.annotate(
            active_assignments_count=Count(
                "assignments",
                filter=Q(assignments__shift_plan=active_shift, assignments__is_active=True),
                distinct=True,
            ),
            supervisors_count=Count(
                "assignments",
                filter=Q(
                    assignments__shift_plan=active_shift,
                    assignments__is_active=True,
                    assignments__role=DoorAssignment.Role.SUPERVISOR,
                ),
                distinct=True,
            ),
            monitors_count=Count(
                "assignments",
                filter=Q(
                    assignments__shift_plan=active_shift,
                    assignments__is_active=True,
                    assignments__role=DoorAssignment.Role.MONITOR,
                ),
                distinct=True,
            ),
            support_count=Count(
                "assignments",
                filter=Q(
                    assignments__shift_plan=active_shift,
                    assignments__is_active=True,
                    assignments__role=DoorAssignment.Role.SUPPORT,
                ),
                distinct=True,
            ),
            technicians_count=Count(
                "assignments",
                filter=Q(
                    assignments__shift_plan=active_shift,
                    assignments__is_active=True,
                    assignments__role=DoorAssignment.Role.TECHNICIAN,
                ),
                distinct=True,
            ),
        ).order_by("door_number")

        assignments = (
            DoorAssignment.objects.select_related(
                "shift_plan",
                "shift_plan__shift_type",
                "door",
                "door__zone",
                "employee",
                "assigned_by",
            )
            .prefetch_related(
                Prefetch(
                    "communication_logs",
                    queryset=CommunicationLog.objects.filter(
                        channel__in=("sms", "whatsapp"),
                    ).order_by("-created_at"),
                    to_attr="assignment_message_logs",
                )
            )
            .filter(
                shift_plan=active_shift,
                is_active=True,
                door__is_active=True,
            )
            .exclude(door__name__iexact="السلام")
            .order_by("door__door_number", "-is_supervisor", "employee__employee_number")
        )

        if scoped_user and not has_all_sections:
            assignments = filter_assignments_for_user(
                assignments,
                request.user,
            )
            doors = filter_doors_for_user(
                doors,
                request.user,
            )

        if query:
            assignments = assignments.filter(
                Q(employee__full_name__icontains=query)
                | Q(employee__employee_number__icontains=query)
                | Q(door__name__icontains=query)
                | Q(door__door_number__icontains=query)
                | Q(notes__icontains=query)
            )
        if role_filter:
            assignments = assignments.filter(role=role_filter)
        if door_filter.isdigit():
            assignments = assignments.filter(door_id=int(door_filter))
        if operational_section_filter in dict(Employee.OperationalSection.choices):
            assignments = assignments.filter(
            employee__operational_section=operational_section_filter
            )

        assignments = list(assignments)
        for assignment in assignments:
            assignment.assignment_message_statuses = {
                log.channel: log.get_status_display()
                for log in assignment.assignment_message_logs
            }

        assignment_employee_ids = (
            ShiftAssignment.objects
            .filter(
                shift_plan=active_shift,
            )
            .values_list("employee_id", flat=True)
        )
        available_employees = (
            Employee.objects
            .filter(
                id__in=assignment_employee_ids,
                is_active=True,
                work_status=Employee.WorkStatus.ACTIVE,
                can_work_on_doors=True,
            )
            .order_by("employee_number")
        )

        if scoped_user and not has_all_sections:
            available_employees = available_employees.filter(
                operational_section__in=allowed_sections,
            )

        if operational_section_filter in dict(Employee.OperationalSection.choices):
            available_employees = available_employees.filter(
            operational_section=operational_section_filter
            )

        report = DistributionService.report(shift_plan=active_shift)

    recent_history = AssignmentHistory.objects.select_related(
        "employee", "door", "changed_by"
    ).filter(
        shift_plan=active_shift,
    ).order_by("-changed_at") if active_shift else AssignmentHistory.objects.none()

    if (
        scoped_user
        and not has_all_sections
        and active_shift
    ):
        recent_history = recent_history.filter(
            assignment__section__in=allowed_sections,
        )

    context = {
        "active_shift": active_shift,
        "assignments": assignments,
        "available_employees": available_employees,
        "doors": doors,
        "q": query,
        "selected_role": role_filter,
        "selected_door": door_filter,
        "selected_operational_section": operational_section_filter,
        "role_choices": DoorAssignment.Role.choices,
        "operational_section_choices": Employee.OperationalSection.choices,
        "distribution_report": report,
        "total_assignments": report.total_assignments if report else 0,
        "supervisor_count": sum(assignment.role == DoorAssignment.Role.SUPERVISOR for assignment in assignments),
        "monitor_count": sum(assignment.role == DoorAssignment.Role.MONITOR for assignment in assignments),
        "support_count": sum(assignment.role == DoorAssignment.Role.SUPPORT for assignment in assignments),
        "technician_count": sum(assignment.role == DoorAssignment.Role.TECHNICIAN for assignment in assignments),
        "covered_doors": report.covered_doors if report else 0,
        "uncovered_doors": report.uncovered_doors if report else doors.count(),
        "recent_history": recent_history[:6],
    }
    return render(request, "distribution/dashboard.html", context)


@login_required
def assignment_history_view(request):
    """سجل التدقيق المؤسسي لجميع تغييرات التوزيع الميداني."""
    _require_distribution_permission(request, PlatformPermissions.VIEW_DISTRIBUTION)
    query = (request.GET.get("q") or "").strip()
    shift_id = (request.GET.get("shift") or "").strip()
    user_id = (request.GET.get("user") or "").strip()
    histories = AssignmentHistory.objects.select_related(
        "assignment", "employee", "door", "shift_plan",
        "shift_plan__shift_type", "changed_by",
    ).order_by("-changed_at")
    scoped_user = has_institutional_scope(request.user)
    allowed_sections = get_allowed_sections(request.user)
    if (
        scoped_user
        and "all" not in allowed_sections
    ):
        histories = histories.filter(
            assignment__section__in=allowed_sections,
        )
    if query:
        histories = histories.filter(
            Q(employee__full_name__icontains=query)
            | Q(employee__employee_number__icontains=query)
            | Q(door__door_number__icontains=query)
            | Q(change_reason__icontains=query)
            | Q(changed_by__username__icontains=query)
        )
    if shift_id.isdigit():
        histories = histories.filter(shift_plan_id=int(shift_id))
    if user_id.isdigit():
        histories = histories.filter(changed_by_id=int(user_id))
    filtered_count = histories.count()
    page_obj = Paginator(histories, 25).get_page(request.GET.get("page"))
    users = AssignmentHistory.objects.filter(
        changed_by__isnull=False
    ).values(
        "changed_by_id", "changed_by__username",
        "changed_by__first_name", "changed_by__last_name",
    ).distinct().order_by("changed_by__username")
    shifts = ShiftPlan.objects.filter(
        audit_assignment_history__isnull=False
    ).select_related("shift_type").distinct().order_by("-date")[:100]
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "distribution/history.html", {
        "histories": page_obj.object_list,
        "page_obj": page_obj,
        "filtered_count": filtered_count,
        "total_count": AssignmentHistory.objects.count(),
        "q": query, "selected_shift": shift_id, "selected_user": user_id,
        "users": users, "shifts": shifts, "query_string": params.urlencode(),
    })


@login_required
@require_POST
def assignment_create_view(request):
    requested_role = (
        request.POST.get("role")
        or DoorAssignment.Role.MONITOR
    ).strip()
    _require_distribution_permission(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    active_shift = _active_shift()
    if not active_shift:
        messages.error(request, "لا توجد وردية نشطة للتوزيع.")
        return redirect("distribution:dashboard")

    employee_id = (request.POST.get("employee_id") or "").strip()
    door_id = (request.POST.get("door_id") or "").strip()
    role = (request.POST.get("role") or DoorAssignment.Role.MONITOR).strip()
    notes = (request.POST.get("notes") or "").strip()

    if not employee_id.isdigit() or not door_id.isdigit():
        messages.error(request, "يجب اختيار الموظف والباب.")
        return redirect("distribution:dashboard")

    if role not in dict(DoorAssignment.Role.choices):
        role = DoorAssignment.Role.MONITOR

    employee = get_object_or_404(
        filter_employees_for_user(Employee.objects, request.user)
        if not request.user.is_superuser else Employee.objects,
        pk=int(employee_id),
    )
    door = get_object_or_404(
        filter_doors_for_user(_available_doors_queryset(), request.user)
        if not request.user.is_superuser else _available_doors_queryset(),
        pk=int(door_id),
    )

    if not _can_manage_assignment_section(
        request.user,
        employee.operational_section,
    ):
        messages.error(
            request,
            "لا تملك صلاحية إدارة تسكين هذا القسم التشغيلي.",
        )
        return redirect("distribution:dashboard")

    try:
        assignment = DistributionService.create_assignment(
            shift_plan=active_shift,
            employee=employee,
            door=door,
            role=role,
            assigned_by=request.user,
            notes=notes,
        )
        door_display = _door_display_name(door)
        log_activity(
            user=request.user,
            module="توزيع الأبواب",
            action=SystemActivityLog.ActionType.CREATE,
            description=f"تم توزيع الموظف {employee.full_name} على {door_display}",
            request=request,
        )
        NotificationService.success(
            title="تم توزيع موظف",
            message=f"تم توزيع {employee.full_name} على {door_display}",
            user=request.user,
            url="/distribution/",
        )
        messages.success(
            request,
            f"تم توزيع {assignment.employee.full_name} على {door_display} بنجاح.",
        )
    except ValidationError as error:
        messages.error(
            request,
            "; ".join(error.messages) if hasattr(error, "messages") else str(error),
        )

    return redirect("distribution:dashboard")


@login_required
@require_POST
def assignment_deactivate_view(request, pk):
    _require_distribution_permission(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    assignment = get_object_or_404(
        filter_assignments_for_user(DoorAssignment.objects, request.user).select_related("employee", "door", "shift_plan")
        if not request.user.is_superuser else DoorAssignment.objects.select_related("employee", "door", "shift_plan"),
        pk=pk,
    )

    if not _can_manage_assignment_section(
        request.user,
        assignment.section,
    ):
        messages.error(
            request,
            "لا تملك صلاحية إدارة تسكين هذا القسم التشغيلي.",
        )
        return redirect("distribution:dashboard")

    try:
        DistributionService.deactivate_assignment(
            assignment=assignment,
            performed_by=request.user,
            reason=(request.POST.get("reason") or "").strip(),
        )
        door_display = _door_display_name(assignment.door)
        log_activity(
            user=request.user,
            module="توزيع الأبواب",
            action=SystemActivityLog.ActionType.UPDATE,
            description=f"تم إلغاء توزيع الموظف {assignment.employee.full_name} من {door_display}",
            request=request,
        )
        NotificationService.warning(
            title="تم إلغاء توزيع موظف",
            message=f"تم إلغاء توزيع {assignment.employee.full_name} من {door_display}",
            user=request.user,
            url="/distribution/",
        )
        messages.warning(
            request,
            f"تم إلغاء توزيع {assignment.employee.full_name} من {door_display}.",
        )
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    return redirect("distribution:dashboard")


@login_required
@require_POST
def assignment_validate_view(request):
    _require_distribution_permission(request, PlatformPermissions.VIEW_DISTRIBUTION)
    active_shift = _active_shift()
    if not active_shift:
        return JsonResponse({"success": False, "error": "لا توجد وردية نشطة."}, status=400)

    report = DistributionService.report(shift_plan=active_shift)
    return JsonResponse({
        "success": True,
        "report": {
            "coverage_percent": report.coverage_percent,
            "quality_score": report.quality_score,
            "quality_label": report.quality_label,
            "doors_without_supervisor": report.doors_without_supervisor,
            "doors_without_monitor": report.doors_without_monitor,
            "warnings": report.warnings,
            "suggestions": report.suggestions,
        },
    })


@login_required
@require_POST
def assignment_auto_assign_view(request):
    _require_all_sections(request)
    active_shift = _active_shift()
    if not active_shift:
        messages.error(request, "لا توجد وردية نشطة.")
        return redirect("distribution:dashboard")

    result = DistributionService.auto_assign(
        shift_plan=active_shift,
        performed_by=request.user,
    )
    messages.success(request, f"تم إنشاء {len(result['created'])} توزيعًا تلقائيًا.")
    if result["skipped"]:
        messages.warning(request, f"تعذر توزيع {len(result['skipped'])} موظفًا.")
    return redirect("distribution:dashboard")


@login_required
@require_POST
def assignment_rebalance_preview_view(request):
    """
    إرجاع معاينة خطة إعادة التوازن دون حفظ أي تغيير.
    """
    _require_all_sections(request)

    active_shift = _active_shift()
    if not active_shift:
        return JsonResponse(
            {
                "success": False,
                "error": "لا توجد وردية نشطة.",
            },
            status=400,
        )

    try:
        plan = DistributionService.build_rebalance_plan(
            shift_plan=active_shift,
        )
    except ValidationError as error:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "; ".join(error.messages)
                    if hasattr(error, "messages")
                    else str(error)
                ),
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "plan": plan,
        }
    )


@login_required
@require_POST
def assignment_rebalance_view(request):
    """
    تنفيذ خطة إعادة التوازن بعد موافقة المستخدم.
    """
    _require_all_sections(request)

    active_shift = _active_shift()
    if not active_shift:
        messages.error(
            request,
            "لا توجد وردية نشطة.",
        )
        return redirect("distribution:dashboard")

    try:
        result = DistributionService.apply_rebalance(
            shift_plan=active_shift,
            performed_by=request.user,
            reason=(
                request.POST.get("reason")
                or "إعادة توازن التوزيع من لوحة التشغيل"
            ).strip(),
        )

        if result["updated"]:
            log_activity(
                user=request.user,
                module="توزيع الأبواب",
                action=SystemActivityLog.ActionType.UPDATE,
                description=(
                    f"تم تنفيذ إعادة توازن التوزيع ونقل "
                    f"{result['updated']} موظفًا"
                ),
                request=request,
            )

            NotificationService.success(
                title="اكتملت إعادة التوازن",
                message=(
                    f"تم نقل {result['updated']} موظفًا "
                    "وفق خطة التوزيع الذكية"
                ),
                user=request.user,
                url="/distribution/",
            )

            messages.success(
                request,
                (
                    f"اكتملت إعادة التوازن بنجاح. "
                    f"تم نقل {result['updated']} موظفًا، "
                    f"وأصبحت التغطية مركزة على "
                    f"{result['after_covered']} أبواب."
                ),
            )
        else:
            messages.info(
                request,
                "لا توجد عمليات نقل مطلوبة؛ التوزيع متوازن بالفعل.",
            )

    except ValidationError as error:
        messages.error(
            request,
            (
                "; ".join(error.messages)
                if hasattr(error, "messages")
                else str(error)
            ),
        )

    return redirect("distribution:dashboard")


@login_required
@require_POST
def assignment_send_sms_view(request):
    _require_distribution_permission(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    return JsonResponse(
        {
            "success": False,
            "error": "رسائل التكليف التشغيلية غير مفعلة.",
        },
        status=503,
    )
