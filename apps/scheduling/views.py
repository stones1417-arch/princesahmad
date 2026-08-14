from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.distribution.services import (
    auto_assign_employee_to_door,
)
from apps.hr.models import Employee
from apps.roles.decorators import permission_required
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_access import (
    filter_employees_for_user,
    get_allowed_sections,
    has_institutional_scope,
)

from .models import (
    Season,
    SeasonalShiftTemplate,
    ShiftAssignment,
    ShiftPlan,
    ShiftType,
)
from .services import activate_shift


# ==================================================
# صلاحيات تطبيق الورديات
# ==================================================

VIEW_SHIFT_PERMISSION = PlatformPermissions.VIEW_SHIFTS
ADD_SHIFT_PERMISSION = PlatformPermissions.CREATE_SHIFT
CHANGE_SHIFT_PERMISSION = PlatformPermissions.CREATE_SHIFT
ACTIVATE_SHIFT_PERMISSION = PlatformPermissions.ACTIVATE_SHIFT
VIEW_ASSIGNMENT_PERMISSION = PlatformPermissions.VIEW_SHIFTS
ADD_ASSIGNMENT_PERMISSION = PlatformPermissions.ASSIGN_EMPLOYEES
CHANGE_ASSIGNMENT_PERMISSION = PlatformPermissions.ASSIGN_EMPLOYEES
DELETE_ASSIGNMENT_PERMISSION = PlatformPermissions.ASSIGN_EMPLOYEES
ADD_SEASONAL_SCHEDULE_PERMISSION = PlatformPermissions.CREATE_SHIFT


def _require_scheduling_scope(request, permission):
    if request.user.is_superuser:
        return
    if (
        not user_has_permission(request.user, permission)
        or not has_institutional_scope(request.user)
    ):
        raise PermissionDenied("لا تملك صلاحية الوصول إلى إدارة الورديات.")


def _scoped_assignments(user):
    queryset = ShiftAssignment.objects.select_related("employee")
    if user.is_superuser:
        return queryset
    return queryset.filter(
        employee__operational_section__in=get_allowed_sections(user)
    )


@login_required
@permission_required(
    VIEW_SHIFT_PERMISSION,
    message="ليس لديك صلاحية عرض مركز إدارة القوى العاملة.",
)
def workforce_center_view(request):
    """مركز موحد للموظفين والتسكين والورديات الاعتيادية والموسمية."""
    _require_scheduling_scope(request, PlatformPermissions.VIEW_SHIFTS)
    today = timezone.localdate()
    employees = filter_employees_for_user(Employee.objects, request.user) if not request.user.is_superuser else Employee.objects.all()
    ready_filter = Q(
        is_active=True,
        work_status=Employee.WorkStatus.ACTIVE,
        can_work_on_doors=True,
    )
    active_shift = (
        ShiftPlan.objects.select_related("shift_type", "season")
        .filter(is_active=True)
        .first()
    )
    active_assignments = ShiftAssignment.objects.none()
    if active_shift:
        active_assignments = (
            ShiftAssignment.objects.select_related("employee")
            .filter(shift_plan=active_shift)
        )
    upcoming_shifts = (
        ShiftPlan.objects.select_related("shift_type", "season")
        .filter(date__gte=today, is_finished=False)
        .annotate(staff_count=Count("assignments"))
        .order_by("date", "start_time")[:8]
    )
    seasons = Season.objects.order_by("-start_date")[:6]
    return render(
        request,
        "scheduling/workforce_center.html",
        {
            "today": today,
            "total_employees": employees.count(),
            "ready_employees": employees.filter(ready_filter).count(),
            "unavailable_employees": employees.exclude(ready_filter).count(),
            "maintenance_employees": employees.filter(
                is_active=True, can_execute_maintenance=True
            ).count(),
            "active_shift": active_shift,
            "active_assignments": active_assignments,
            "confirmed_assignments": active_assignments.filter(is_confirmed=True).count(),
            "upcoming_shifts": upcoming_shifts,
            "seasons": seasons,
            "active_seasons": Season.objects.filter(
                status=Season.SeasonStatus.ACTIVE
            ).count(),
        },
    )


# ==================================================
# إنشاء أنواع الورديات الافتراضية
# ==================================================

def ensure_default_shift_types():
    """
    إنشاء أنواع الورديات الأساسية أو تحديث
    أوقاتها الرسمية.
    """
    defaults = [
        (
            "الفجر",
            time(2, 0),
            time(8, 15),
        ),
        (
            "الضحى",
            time(7, 45),
            time(14, 30),
        ),
        (
            "المسائية",
            time(14, 45),
            time(20, 30),
        ),
        (
            "المشتركة",
            time(21, 0),
            time(2, 0),
        ),
    ]

    for (
        name,
        start_time,
        end_time,
    ) in defaults:
        ShiftType.objects.update_or_create(
            name=name,
            defaults={
                "start_time": start_time,
                "end_time": end_time,
            },
        )

    old_names = [
        "فجر",
        "المساندة",
    ]

    for old_name in old_names:
        old_shift = (
            ShiftType.objects
            .filter(
                name=old_name
            )
            .first()
        )

        if (
            old_shift
            and not old_shift.shift_plans.exists()
        ):
            old_shift.delete()


# ==================================================
# إنشاء خطط ورديات اليوم
# ==================================================

def ensure_today_shift_plans():
    """
    التأكد من وجود خطط الورديات اليومية الأربع
    لليوم الحالي وفق نموذج ShiftPlan الفعلي.
    """
    ensure_default_shift_types()

    today = timezone.localdate()

    official_names = [
        "الفجر",
        "الضحى",
        "المسائية",
        "المشتركة",
    ]

    shift_types = (
        ShiftType.objects
        .filter(
            name__in=official_names
        )
        .order_by(
            "start_time",
            "id",
        )
    )

    for shift_type in shift_types:
        ShiftPlan.objects.get_or_create(
            date=today,
            shift_type=shift_type,
            category=(
                ShiftPlan
                .ShiftCategory
                .DAILY
            ),
            season=None,
            seasonal_template=None,
            defaults={
                "start_time": None,
                "end_time": None,
                "crosses_midnight": False,
                "notes": "وردية اليوم",
            },
        )


# ==================================================
# عرض الوردية النشطة
# ==================================================

@login_required
@permission_required(
    VIEW_SHIFT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "عرض الوردية الحالية."
    ),
)
def current_shift_view(request):
    """
    عرض الوردية النشطة حاليًا.
    """
    from apps.dashboard.views import build_dashboard_context

    context = build_dashboard_context(request)
    context["show_shift_dashboard"] = True

    return render(
        request,
        "dashboard/index.html",
        context,
    )


# ==================================================
# عرض حالة ورديات اليوم
# ==================================================

@login_required
@permission_required(
    VIEW_SHIFT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "عرض حالة الورديات."
    ),
)
def shifts_status_view(request):
    """
    عرض حالة ورديات اليوم.
    """
    ensure_today_shift_plans()

    today = timezone.localdate()

    official_names = [
        "الفجر",
        "الضحى",
        "المسائية",
        "المشتركة",
    ]

    shifts = (
        ShiftPlan.objects
        .select_related(
            "shift_type",
            "season",
            "seasonal_template",
        )
        .filter(
            date=today,
            shift_type__name__in=(
                official_names
            ),
        )
        .order_by(
            "shift_type__start_time",
            "shift_type__id",
        )
    )

    active_shift = (
        ShiftPlan.objects
        .select_related(
            "shift_type",
            "season",
            "seasonal_template",
        )
        .filter(
            is_active=True
        )
        .first()
    )

    shift_types = (
        ShiftType.objects
        .filter(
            name__in=official_names
        )
        .order_by(
            "start_time",
            "id",
        )
    )

    return render(
        request,
        "scheduling/shifts_status.html",
        {
            "shifts": shifts,
            "active_shift": active_shift,
            "shift_types": shift_types,
            "today": today,
            "shifts_total": shifts.count(),
            "shifts_active_count": shifts.filter(is_active=True).count(),
            "shifts_finished_count": shifts.filter(is_finished=True).count(),
            "shifts_ready_count": shifts.filter(is_active=False, is_finished=False).count(),
        },
    )


# ==================================================
# تفعيل وردية
# ==================================================

@login_required
@require_POST
@permission_required(
    ACTIVATE_SHIFT_PERMISSION,
    ajax=True,
    message=(
        "ليس لديك صلاحية "
        "تفعيل الورديات."
    ),
)
def activate_shift_ajax(
    request,
    pk,
):
    """
    تفعيل وردية محددة.
    """
    _require_scheduling_scope(request, PlatformPermissions.ACTIVATE_SHIFT)
    shift = get_object_or_404(
        ShiftPlan.objects.select_related(
            "shift_type",
            "season",
            "seasonal_template",
        ),
        pk=pk,
    )

    try:
        activate_shift(
            shift
        )

        shift.refresh_from_db()

    except ValidationError as error:
        error_message = (
            "؛ ".join(error.messages)
            if hasattr(
                error,
                "messages",
            )
            else str(error)
        )

        return JsonResponse(
            {
                "success": False,
                "error": error_message,
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "shift": {
                "id": shift.id,
                "is_active": (
                    shift.is_active
                ),
                "label": str(shift),
                "date": (
                    shift.date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "shift_type": (
                    shift.shift_type.name
                ),
                "notes": (
                    shift.notes or ""
                ),
                "category": (
                    shift.category
                ),
                "category_label": (
                    shift.get_category_display()
                ),
                "start_time": (
                    shift
                    .effective_start_time
                    .strftime("%H:%M")
                    if shift.effective_start_time
                    else ""
                ),
                "end_time": (
                    shift
                    .effective_end_time
                    .strftime("%H:%M")
                    if shift.effective_end_time
                    else ""
                ),
            },
        }
    )


# ==================================================
# إنشاء أو تحديث وردية اعتيادية
# ==================================================

@login_required
@require_POST
@permission_required(
    CHANGE_SHIFT_PERMISSION,
    ajax=True,
    message=(
        "ليس لديك صلاحية "
        "إنشاء أو تحديث الورديات."
    ),
)
def upsert_shift_plan_ajax(request):
    """
    إنشاء خطة وردية يومية أو تحديثها.
    """
    _require_scheduling_scope(request, PlatformPermissions.CREATE_SHIFT)
    ensure_default_shift_types()

    date_str = (
        request.POST.get("date")
        or ""
    ).strip()

    shift_type_id = (
        request.POST.get(
            "shift_type_id"
        )
        or ""
    ).strip()

    notes = (
        request.POST.get("notes")
        or ""
    ).strip()

    make_active = (
        request.POST.get(
            "make_active"
        )
        or "0"
    ).strip()

    if (
        not date_str
        or not shift_type_id
    ):
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "التاريخ ونوع "
                    "الوردية مطلوبان"
                ),
            },
            status=400,
        )

    try:
        date_value = (
            datetime.strptime(
                date_str,
                "%Y-%m-%d",
            ).date()
        )

    except ValueError:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "صيغة التاريخ "
                    "غير صحيحة"
                ),
            },
            status=400,
        )

    try:
        shift_type_id_int = int(
            shift_type_id
        )

    except (
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "نوع الوردية "
                    "غير صحيح"
                ),
            },
            status=400,
        )

    shift_type = get_object_or_404(
        ShiftType,
        pk=shift_type_id_int,
    )

    # تحفظ الورديات اليومية دون أوقات مكررة داخل ShiftPlan.
    # الأوقات الفعلية تُقرأ من ShiftType عبر effective_start_time
    # وeffective_end_time، وبذلك لا تتعارض مع فحص التداخل.
    start_time = None
    end_time = None
    crosses_midnight = False

    try:
        with transaction.atomic():
            shift, created = (
                ShiftPlan.objects
                .get_or_create(
                    date=date_value,
                    shift_type=shift_type,
                    category=(
                        ShiftPlan
                        .ShiftCategory
                        .DAILY
                    ),
                    season=None,
                    seasonal_template=None,
                    defaults={
                        "start_time": start_time,
                        "end_time": end_time,
                        "crosses_midnight": (
                            crosses_midnight
                        ),
                        "notes": (
                            notes
                            or "وردية مجدولة"
                        ),
                        "created_by": (
                            request.user
                        ),
                    },
                )
            )

            if not created:
                update_fields = []

                new_notes = (
                    notes
                    or shift.notes
                )

                if shift.notes != new_notes:
                    shift.notes = new_notes
                    update_fields.append(
                        "notes"
                    )

                # لا يتم تعديل أوقات وردية يومية موجودة هنا.
                # يظل ShiftType هو المصدر الرسمي لأوقات الوردية.

                if update_fields:
                    shift.save(
                        update_fields=(
                            update_fields
                        )
                    )

            if make_active == "1":
                activate_shift(
                    shift
                )

                shift.refresh_from_db()

    except ValidationError as error:
        error_message = (
            "؛ ".join(error.messages)
            if hasattr(
                error,
                "messages",
            )
            else str(error)
        )

        return JsonResponse(
            {
                "success": False,
                "error": error_message,
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "created": created,
            "shift": {
                "id": shift.id,
                "is_active": (
                    shift.is_active
                ),
                "is_finished": (
                    shift.is_finished
                ),
                "date": (
                    shift.date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "shift_type": (
                    shift.shift_type.name
                ),
                "shift_type_id": (
                    shift.shift_type_id
                ),
                "notes": (
                    shift.notes or ""
                ),
                "label": str(shift),
                "category": (
                    shift.category
                ),
                "category_label": (
                    shift.get_category_display()
                ),
                "start_time": (
                    shift.effective_start_time.strftime(
                        "%H:%M"
                    )
                    if shift.effective_start_time
                    else ""
                ),
                "end_time": (
                    shift.effective_end_time.strftime(
                        "%H:%M"
                    )
                    if shift.effective_end_time
                    else ""
                ),
                "crosses_midnight": (
                    shift.crosses_midnight
                ),
            },
        }
    )


# ==================================================
# عرض تسكين موظفي الوردية
# ==================================================

@login_required
@permission_required(
    VIEW_ASSIGNMENT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "عرض تسكين موظفي الورديات."
    ),
)
def shift_assignment_list_view(
    request,
):
    """
    عرض الموظفين المسكنين
    في الوردية النشطة أو في وردية محددة من القائمة.
    """
    _require_scheduling_scope(request, PlatformPermissions.VIEW_SHIFTS)
    shift_queryset = (
        ShiftPlan.objects
        .select_related(
            "shift_type",
            "season",
            "seasonal_template",
        )
        .filter(
            is_finished=False,
        )
        .order_by(
            "date",
            "shift_type__start_time",
            "shift_type__id",
        )
    )
    active_shift = shift_queryset.filter(is_active=True).first()
    selected_shift = active_shift or shift_queryset.first()

    assignments = ShiftAssignment.objects.none()
    available_employees = Employee.objects.none()
    confirmed_count = 0

    if selected_shift:
        assignments = (
            _scoped_assignments(request.user)
            .select_related(
                "employee",
                "shift_plan",
                "shift_plan__shift_type",
            )
            .filter(
                shift_plan=selected_shift,
            )
            .order_by(
                "role",
                "employee__employee_number",
            )
        )

        available_employees = (
            (filter_employees_for_user(Employee.objects, request.user) if not request.user.is_superuser else Employee.objects)
            .filter(
                is_active=True,
                work_status=Employee.WorkStatus.ACTIVE,
                can_work_on_doors=True,
            )
            .exclude(
                shift_assignments__shift_plan=selected_shift,
            )
            .order_by(
                "employee_number",
            )
            .distinct()
        )

        confirmed_count = (
            assignments.filter(
                is_confirmed=True,
            ).count()
        )

    assignment_groups = []
    for shift in shift_queryset:
        shift_assignments = (
            _scoped_assignments(request.user)
            .select_related(
                "employee",
                "shift_plan",
                "shift_plan__shift_type",
            )
            .filter(
                shift_plan=shift,
            )
            .order_by(
                "role",
                "employee__employee_number",
            )
        )
        assignment_groups.append(
            {
                "shift": shift,
                "assignments": shift_assignments,
            }
        )

    return render(
        request,
        "scheduling/shift_assignments.html",
        {
            "active_shift": active_shift,
            "selected_shift": selected_shift,
            "assignments": assignments,
            "available_employees": available_employees,
            "confirmed_count": confirmed_count,
            "assignment_groups": assignment_groups,
            "shift_choices": list(shift_queryset),
            "role_choices": (
                ShiftAssignment
                .OperationalRole
                .choices
            ),
        },
    )


# ==================================================
# إضافة موظف إلى الوردية
# ==================================================

@login_required
@require_POST
@permission_required(
    ADD_ASSIGNMENT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "تسكين الموظفين على الورديات."
    ),
)
def shift_assignment_create_view(
    request,
):
    """
    تسكين موظف في وردية محددة بشكل صريح.
    """
    _require_scheduling_scope(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    active_shift = (
        ShiftPlan.objects
        .select_related(
            "shift_type"
        )
        .filter(
            is_active=True,
            is_finished=False,
        )
        .first()
    )

    shift_plan_id = (
        request.POST.get("shift_plan_id")
        or request.POST.get("shift_id")
        or ""
    ).strip()

    if not shift_plan_id.isdigit():
        messages.error(
            request,
            "يجب اختيار وردية صحيحة قبل التسكين.",
        )
        return redirect("scheduling:assignments")

    shift_plan = get_object_or_404(
        ShiftPlan.objects.select_related("shift_type"),
        pk=int(shift_plan_id),
        is_finished=False,
    )

    employee_id = (
        request.POST.get(
            "employee_id"
        )
        or ""
    ).strip()

    role = (
        request.POST.get("role")
        or ""
    ).strip()

    notes = (
        request.POST.get("notes")
        or ""
    ).strip()

    if not employee_id.isdigit():
        messages.error(
            request,
            "اختيار الموظف غير صحيح",
        )

        return redirect(
            "scheduling:assignments"
        )

    valid_roles = dict(
        ShiftAssignment
        .OperationalRole
        .choices
    )

    if role not in valid_roles:
        messages.error(
            request,
            "الدور التشغيلي غير صحيح",
        )

        return redirect(
            "scheduling:assignments"
        )

    employee = get_object_or_404(
        filter_employees_for_user(Employee.objects, request.user) if not request.user.is_superuser else Employee.objects,
        pk=int(employee_id),
        is_active=True,
    )

    assignment_exists = (
        ShiftAssignment.objects
        .filter(
            shift_plan=shift_plan,
            employee=employee,
        )
        .exists()
    )

    if assignment_exists:
        messages.warning(
            request,
            (
                "الموظف مسكن مسبقًا "
                "في هذه الوردية"
            ),
        )

        return redirect(
            "scheduling:assignments"
        )

    single_roles = [
        ShiftAssignment
        .OperationalRole
        .SHIFT_HEAD,

        ShiftAssignment
        .OperationalRole
        .SHIFT_DEPUTY,
    ]

    if role in single_roles:
        role_exists = (
            ShiftAssignment.objects
            .filter(
                shift_plan=shift_plan,
                role=role,
            )
            .exists()
        )

        if role_exists:
            messages.error(
                request,
                (
                    "لا يمكن تكرار رئيس "
                    "الوردية أو نائب الوردية "
                    "في نفس الوردية"
                ),
            )

            return redirect(
                "scheduling:assignments"
            )

    try:
        with transaction.atomic():
            assignment = (
                ShiftAssignment.objects
                .create(
                    shift_plan=shift_plan,
                    employee=employee,
                    role=role,
                    notes=notes,
                )
            )

            auto_assign_employee_to_door(
                shift_plan=shift_plan,
                employee=employee,
            )

    except ValidationError as error:
        if hasattr(
            error,
            "message_dict",
        ):
            error_message = "؛ ".join(
                message
                for messages_list
                in error.message_dict.values()
                for message
                in messages_list
            )

        elif hasattr(
            error,
            "messages",
        ):
            error_message = "؛ ".join(
                error.messages
            )

        else:
            error_message = str(error)

        messages.error(
            request,
            error_message,
        )

        return redirect(
            "scheduling:assignments"
        )

    messages.success(
        request,
        (
            f"تم تسكين "
            f"{assignment.employee.full_name} "
            f"في وردية {shift_plan.shift_type.name} "
            f"بدور "
            f"{assignment.get_role_display()}"
        ),
    )

    return redirect(
        "scheduling:assignments"
    )


# ==================================================
# تأكيد تسكين موظف
# ==================================================

@login_required
@require_POST
@permission_required(
    CHANGE_ASSIGNMENT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "تأكيد تسكين الموظفين."
    ),
)
def shift_assignment_confirm_view(
    request,
    pk,
):
    """
    تأكيد تسكين موظف.
    """
    _require_scheduling_scope(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    assignment = get_object_or_404(
        _scoped_assignments(request.user)
        .select_related(
            "employee"
        ),
        pk=pk,
    )

    if not assignment.is_confirmed:
        assignment.is_confirmed = True

        assignment.save(
            update_fields=[
                "is_confirmed",
            ]
        )

    messages.success(
        request,
        (
            f"تم تأكيد تسكين "
            f"{assignment.employee.full_name}"
        ),
    )

    return redirect(
        "scheduling:assignments"
    )


# ==================================================
# حذف تسكين موظف
# ==================================================

@login_required
@require_POST
@permission_required(
    DELETE_ASSIGNMENT_PERMISSION,
    message=(
        "ليس لديك صلاحية "
        "حذف تسكين الموظفين."
    ),
)
def shift_assignment_delete_view(
    request,
    pk,
):
    """
    حذف تسكين موظف.
    """
    _require_scheduling_scope(request, PlatformPermissions.ASSIGN_EMPLOYEES)
    assignment = get_object_or_404(
        _scoped_assignments(request.user)
        .select_related(
            "employee",
            "shift_plan",
        ),
        pk=pk,
    )

    employee_name = (
        assignment.employee.full_name
    )

    assignment.delete()

    messages.success(
        request,
        (
            f"تم إلغاء تسكين "
            f"{employee_name}"
        ),
    )

    return redirect(
        "scheduling:assignments"
    )


# ==================================================
# إنشاء الجدولة الموسمية
# ==================================================

@login_required
@require_POST
@permission_required(
    ADD_SEASONAL_SCHEDULE_PERMISSION,
    ajax=True,
    message=(
        "ليس لديك صلاحية "
        "إنشاء الورديات الموسمية."
    ),
)
def create_seasonal_schedule_ajax(
    request,
):
    """
    إنشاء موسم وقوالب ورديات موسمية ثم توليد
    خطط الورديات خلال فترة الموسم.

    يعتمد على النماذج الفعلية:
    - Season
    - SeasonalShiftTemplate
    - ShiftPlan
    """
    _require_scheduling_scope(request, PlatformPermissions.CREATE_SHIFT)
    ensure_default_shift_types()

    season_type = (
        request.POST.get(
            "season_type"
        )
        or ""
    ).strip()

    name = (
        request.POST.get("name")
        or ""
    ).strip()

    start_date_str = (
        request.POST.get(
            "start_date"
        )
        or ""
    ).strip()

    end_date_str = (
        request.POST.get(
            "end_date"
        )
        or ""
    ).strip()

    notes = (
        request.POST.get("notes")
        or ""
    ).strip()

    allowed_seasons = dict(
        Season.SeasonType.choices
    )

    if season_type not in allowed_seasons:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "يجب اختيار نوع موسم صحيح."
                ),
            },
            status=400,
        )

    if not name:
        name = (
            f"ورديات "
            f"{allowed_seasons[season_type]}"
        )

    if (
        not start_date_str
        or not end_date_str
    ):
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "تاريخ بداية الموسم "
                    "وتاريخ النهاية مطلوبان."
                ),
            },
            status=400,
        )

    try:
        start_date = (
            datetime.strptime(
                start_date_str,
                "%Y-%m-%d",
            ).date()
        )

        end_date = (
            datetime.strptime(
                end_date_str,
                "%Y-%m-%d",
            ).date()
        )

    except ValueError:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "صيغة تاريخ الموسم "
                    "غير صحيحة."
                ),
            },
            status=400,
        )

    if end_date < start_date:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "تاريخ نهاية الموسم "
                    "يجب أن يكون بعد البداية."
                ),
            },
            status=400,
        )

    season_days = (
        end_date - start_date
    ).days + 1

    if season_days > 90:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "لا يمكن أن تتجاوز "
                    "فترة الموسم 90 يومًا."
                ),
            },
            status=400,
        )

    shift_types = list(
        ShiftType.objects
        .filter(
            name__in=[
                "الفجر",
                "الضحى",
                "المسائية",
                "المشتركة",
            ]
        )
        .order_by(
            "start_time",
            "id",
        )
    )

    selected_shift_times = []

    for ordering, shift_type in enumerate(
        shift_types,
        start=1,
    ):
        enabled = (
            request.POST.get(
                (
                    f"shift_"
                    f"{shift_type.id}"
                    f"_enabled"
                ),
                "0",
            )
            or "0"
        ).strip()

        if enabled != "1":
            continue

        start_value = (
            request.POST.get(
                (
                    f"shift_"
                    f"{shift_type.id}"
                    f"_start"
                )
            )
            or ""
        ).strip()

        end_value = (
            request.POST.get(
                (
                    f"shift_"
                    f"{shift_type.id}"
                    f"_end"
                )
            )
            or ""
        ).strip()

        if (
            not start_value
            or not end_value
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "حدد وقت البداية "
                        "والنهاية لوردية "
                        f"{shift_type.name}."
                    ),
                },
                status=400,
            )

        try:
            seasonal_start_time = (
                datetime.strptime(
                    start_value,
                    "%H:%M",
                ).time()
            )

            seasonal_end_time = (
                datetime.strptime(
                    end_value,
                    "%H:%M",
                ).time()
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "صيغة وقت وردية "
                        f"{shift_type.name} "
                        "غير صحيحة."
                    ),
                },
                status=400,
            )

        if (
            seasonal_start_time
            == seasonal_end_time
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "وقت بداية ونهاية "
                        "وردية "
                        f"{shift_type.name} "
                        "لا يمكن أن يكونا "
                        "متساويين."
                    ),
                },
                status=400,
            )

        crosses_midnight = (
            seasonal_end_time
            < seasonal_start_time
        )

        selected_shift_times.append(
            {
                "shift_type": shift_type,
                "name": shift_type.name,
                "start_time": (
                    seasonal_start_time
                ),
                "end_time": (
                    seasonal_end_time
                ),
                "crosses_midnight": (
                    crosses_midnight
                ),
                "ordering": ordering,
            }
        )

    if not selected_shift_times:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "يجب اختيار وردية "
                    "موسمية واحدة على الأقل."
                ),
            },
            status=400,
        )

    try:
        with transaction.atomic():
            season = Season(
                name=name,
                season_type=season_type,
                start_date=start_date,
                end_date=end_date,
                status=(
                    Season
                    .SeasonStatus
                    .ACTIVE
                ),
                notes=notes,
                created_by=request.user,
                activated_by=request.user,
                activated_at=timezone.now(),
            )

            season.full_clean()
            season.save()

            templates = []

            for item in selected_shift_times:
                template = (
                    SeasonalShiftTemplate(
                        season=season,
                        name=item["name"],
                        start_time=(
                            item["start_time"]
                        ),
                        end_time=(
                            item["end_time"]
                        ),
                        crosses_midnight=(
                            item[
                                "crosses_midnight"
                            ]
                        ),
                        ordering=(
                            item["ordering"]
                        ),
                        notes=notes,
                        is_active=True,
                    )
                )

                template.full_clean()
                template.save()

                templates.append(
                    (
                        item["shift_type"],
                        template,
                    )
                )

            created_count = 0
            existing_count = 0
            updated_count = 0

            current_date = start_date

            while current_date <= end_date:
                for (
                    shift_type,
                    template,
                ) in templates:
                    shift_plan, created = (
                        ShiftPlan.objects
                        .get_or_create(
                            date=current_date,
                            shift_type=shift_type,
                            category=(
                                ShiftPlan
                                .ShiftCategory
                                .SEASONAL
                            ),
                            season=season,
                            seasonal_template=(
                                template
                            ),
                            defaults={
                                "start_time": (
                                    template
                                    .start_time
                                ),
                                "end_time": (
                                    template
                                    .end_time
                                ),
                                "crosses_midnight": (
                                    template
                                    .crosses_midnight
                                ),
                                "notes": (
                                    notes
                                    or (
                                        "وردية موسمية - "
                                        f"{season.get_season_type_display()}"
                                    )
                                ),
                                "created_by": (
                                    request.user
                                ),
                            },
                        )
                    )

                    if created:
                        created_count += 1
                        continue

                    existing_count += 1
                    update_fields = []

                    if (
                        shift_plan.start_time
                        != template.start_time
                    ):
                        shift_plan.start_time = (
                            template.start_time
                        )
                        update_fields.append(
                            "start_time"
                        )

                    if (
                        shift_plan.end_time
                        != template.end_time
                    ):
                        shift_plan.end_time = (
                            template.end_time
                        )
                        update_fields.append(
                            "end_time"
                        )

                    if (
                        shift_plan
                        .crosses_midnight
                        != template
                        .crosses_midnight
                    ):
                        shift_plan.crosses_midnight = (
                            template
                            .crosses_midnight
                        )
                        update_fields.append(
                            "crosses_midnight"
                        )

                    seasonal_note = (
                        notes
                        or (
                            "وردية موسمية - "
                            f"{season.get_season_type_display()}"
                        )
                    )

                    if (
                        shift_plan.notes
                        != seasonal_note
                    ):
                        shift_plan.notes = (
                            seasonal_note
                        )
                        update_fields.append(
                            "notes"
                        )

                    if update_fields:
                        shift_plan.save(
                            update_fields=(
                                update_fields
                            )
                        )
                        updated_count += 1

                current_date += timedelta(
                    days=1
                )

    except ValidationError as error:
        if hasattr(
            error,
            "message_dict",
        ):
            error_message = "؛ ".join(
                message
                for messages_list
                in error.message_dict.values()
                for message
                in messages_list
            )

        elif hasattr(
            error,
            "messages",
        ):
            error_message = "؛ ".join(
                error.messages
            )

        else:
            error_message = str(error)

        return JsonResponse(
            {
                "success": False,
                "error": error_message,
            },
            status=400,
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "حدث خطأ أثناء إنشاء "
                    "الورديات الموسمية."
                ),
            },
            status=500,
        )

    return JsonResponse(
        {
            "success": True,
            "message": (
                "تم إنشاء موسم "
                f"{season.get_season_type_display()} "
                "وتوليد وردياته بنجاح."
            ),
            "schedule": {
                "id": season.id,
                "name": season.name,
                "season_label": (
                    season
                    .get_season_type_display()
                ),
                "start_date": (
                    season.start_date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "end_date": (
                    season.end_date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "days_count": season_days,
                "selected_shifts_count": (
                    len(
                        selected_shift_times
                    )
                ),
                "created_plans_count": (
                    created_count
                ),
                "existing_plans_count": (
                    existing_count
                ),
                "updated_plans_count": (
                    updated_count
                ),
            },
        }
    )
