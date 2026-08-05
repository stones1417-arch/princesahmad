from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.notification_service import NotificationService
from apps.core.permissions import require_staff
from apps.core.sms_service import SmsService
from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan
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


@login_required
def distribution_dashboard_view(request):
    require_staff(request.user)
    active_shift = _active_shift()
    doors = _available_doors_queryset()

    assignments = DoorAssignment.objects.none()
    available_employees = Employee.objects.none()
    report = None

    query = (request.GET.get("q") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    door_filter = (request.GET.get("door") or "").strip()

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
            .filter(
                shift_plan=active_shift,
                is_active=True,
                door__is_active=True,
                door__door_number__gte=1,
                door__door_number__lte=41,
            )
            .exclude(door__name__iexact="السلام")
            .order_by("door__door_number", "-is_supervisor", "employee__employee_number")
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

        available_ids = [
            employee.id
            for employee in DistributionService.eligible_employees(shift_plan=active_shift)
        ]
        available_employees = Employee.objects.filter(id__in=available_ids).order_by("employee_number")
        report = DistributionService.report(shift_plan=active_shift)

    context = {
        "active_shift": active_shift,
        "assignments": assignments,
        "available_employees": available_employees,
        "doors": doors,
        "q": query,
        "selected_role": role_filter,
        "selected_door": door_filter,
        "role_choices": DoorAssignment.Role.choices,
        "distribution_report": report,
        "total_assignments": report.total_assignments if report else 0,
        "supervisor_count": assignments.filter(role=DoorAssignment.Role.SUPERVISOR).count() if active_shift else 0,
        "monitor_count": assignments.filter(role=DoorAssignment.Role.MONITOR).count() if active_shift else 0,
        "support_count": assignments.filter(role=DoorAssignment.Role.SUPPORT).count() if active_shift else 0,
        "technician_count": assignments.filter(role=DoorAssignment.Role.TECHNICIAN).count() if active_shift else 0,
        "covered_doors": report.covered_doors if report else 0,
        "uncovered_doors": report.uncovered_doors if report else doors.count(),
        "recent_history": AssignmentHistory.objects.select_related(
            "employee", "door", "changed_by"
        ).filter(shift_plan=active_shift).order_by("-changed_at")[:6]
        if active_shift else AssignmentHistory.objects.none(),
    }
    return render(request, "distribution/dashboard.html", context)


@login_required
def assignment_history_view(request):
    """سجل التدقيق المؤسسي لجميع تغييرات التوزيع الميداني."""
    require_staff(request.user)
    query = (request.GET.get("q") or "").strip()
    shift_id = (request.GET.get("shift") or "").strip()
    user_id = (request.GET.get("user") or "").strip()
    histories = AssignmentHistory.objects.select_related(
        "assignment", "employee", "door", "shift_plan",
        "shift_plan__shift_type", "changed_by",
    ).order_by("-changed_at")
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
    require_staff(request.user)
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

    employee = get_object_or_404(Employee, pk=int(employee_id))
    door = get_object_or_404(_available_doors_queryset(), pk=int(door_id))

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
    require_staff(request.user)
    assignment = get_object_or_404(
        DoorAssignment.objects.select_related("employee", "door", "shift_plan"),
        pk=pk,
    )
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
    require_staff(request.user)
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
    require_staff(request.user)
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
    require_staff(request.user)

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
    require_staff(request.user)

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
    require_staff(request.user)
    employee_id = (request.POST.get("employee_id") or "").strip()
    message_text = (request.POST.get("message") or "").strip()

    if not employee_id.isdigit():
        return JsonResponse({"success": False, "error": "لم يتم تحديد الموظف بصورة صحيحة."}, status=400)
    if not message_text:
        return JsonResponse({"success": False, "error": "رسالة التكليف فارغة."}, status=400)

    employee = get_object_or_404(Employee, pk=int(employee_id), is_active=True)
    phone_number = (employee.phone_number or "").strip()
    if not phone_number:
        return JsonResponse(
            {"success": False, "error": f"رقم جوال الموظف {employee.full_name} غير مسجل."},
            status=400,
        )

    result = SmsService.send(
        recipient=phone_number,
        message=message_text,
        correlation_id=f"door-assignment-employee-{employee.id}",
    )
    if not result.success:
        return JsonResponse(
            {"success": False, "error": result.error or "تعذر إرسال الرسالة."},
            status=400,
        )

    log_activity(
        user=request.user,
        module="توزيع الأبواب",
        action=SystemActivityLog.ActionType.CREATE,
        description=f"تم إرسال رسالة تكليف SMS إلى {employee.full_name} على الرقم {phone_number}",
        request=request,
    )
    NotificationService.success(
        title="تم إرسال رسالة التكليف",
        message=f"تم إرسال رسالة SMS إلى الموظف {employee.full_name}",
        user=request.user,
        url="/distribution/",
    )
    return JsonResponse({
        "success": True,
        "message": "تم إرسال رسالة التكليف بنجاح.",
        "message_id": result.message_id,
    })
