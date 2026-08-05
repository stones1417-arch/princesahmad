from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.notification_service import NotificationService
from apps.core.permissions import require_staff
from apps.dashboard.activity_logger import log_activity
from apps.dashboard.models import SystemActivityLog
from apps.hr.models import Employee
from apps.scheduling.models import ShiftType

from .models import Break, BreakHistory


# ==========================================================
# الأدوات المساعدة
# ==========================================================


def _get_client_ip(request: HttpRequest) -> str | None:
    """
    استخراج عنوان IP الحقيقي للمستخدم.

    عند تشغيل المشروع خلف Reverse Proxy يجب ضبط البروكسي
    ليعيد كتابة X-Forwarded-For بصورة موثوقة.
    """

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def _first_validation_message(
    error: ValidationError,
) -> str:
    """
    استخراج أول رسالة واضحة من ValidationError.
    """

    if hasattr(error, "message_dict"):
        message_dict = error.message_dict

        for field_messages in message_dict.values():
            if field_messages:
                return str(field_messages[0])

    if hasattr(error, "messages") and error.messages:
        return str(error.messages[0])

    return str(error)


def _post_value(
    request: HttpRequest,
    field_name: str,
) -> str:
    """
    قراءة قيمة نصية من POST مع إزالة المسافات.
    """

    return str(
        request.POST.get(field_name) or ""
    ).strip()


def _redirect_to_breaks_list() -> HttpResponse:
    return redirect("breaks:list")


def _schedule_notification(
    callback: Callable[[], None],
) -> None:
    """
    تشغيل الإشعار بعد نجاح المعاملة فقط.

    بهذه الطريقة لا يتم إرسال إشعار إذا حصل rollback.
    """

    transaction.on_commit(callback)


def _record_break_history(
    *,
    break_obj: Break | None,
    break_id_snapshot: int | None,
    employee: Employee,
    shift_type: ShiftType,
    action: str,
    request: HttpRequest,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason: str = "",
) -> BreakHistory:
    """
    إنشاء سجل تدقيق لعملية على الراحة.
    """

    return BreakHistory.objects.create(
        break_record=break_obj,
        break_id_snapshot=break_id_snapshot,
        employee=employee,
        shift_type=shift_type,
        action=action,
        old_value=old_value or {},
        new_value=new_value or {},
        performed_by=request.user,
        reason=str(reason or "").strip(),
        ip_address=_get_client_ip(request),
    )


def _validate_break_choices(
    *,
    job_title: str,
    rest_days: str,
) -> None:
    """
    التحقق من قيم القوائم قبل التعامل مع قاعدة البيانات.
    """

    valid_job_titles = dict(
        Break.BreakJobTitle.choices
    )

    valid_rest_days = dict(
        Break.RestDays.choices
    )

    errors: dict[str, str] = {}

    if job_title not in valid_job_titles:
        errors["job_title"] = (
            "المسمى التشغيلي غير صحيح."
        )

    if rest_days not in valid_rest_days:
        errors["rest_days"] = (
            "أيام الراحة غير صحيحة."
        )

    if errors:
        raise ValidationError(errors)


def _get_active_employee(
    employee_id: str,
) -> Employee:
    """
    جلب موظف نشط بعد التحقق من المعرف.
    """

    if not employee_id.isdigit():
        raise ValidationError(
            {
                "employee": (
                    "يجب اختيار موظف صحيح."
                )
            }
        )

    return get_object_or_404(
        Employee,
        pk=int(employee_id),
        is_active=True,
    )


def _get_shift_type(
    shift_type_id: str,
) -> ShiftType:
    """
    جلب نوع الوردية بعد التحقق من المعرف.
    """

    if not shift_type_id.isdigit():
        raise ValidationError(
            {
                "shift_type": (
                    "يجب اختيار نوع وردية صحيح."
                )
            }
        )

    return get_object_or_404(
        ShiftType,
        pk=int(shift_type_id),
    )


def _filtered_breaks_queryset(
    request: HttpRequest,
) -> tuple[QuerySet[Break], dict[str, str]]:
    """
    إنشاء QuerySet الراحات حسب الفلاتر الموجودة في الطلب.
    """

    q = _post_value(request, "q")
    shift_type_id = _post_value(
        request,
        "shift_type",
    )
    rest_days = _post_value(
        request,
        "rest_days",
    )
    job_title = _post_value(
        request,
        "job_title",
    )
    active_filter = _post_value(
        request,
        "active",
    )

    queryset = (
        Break.objects
        .select_related(
            "employee",
            "shift_type",
        )
        .all()
    )

    if q:
        queryset = queryset.filter(
            Q(
                employee__full_name__icontains=q
            )
            | Q(
                employee__employee_number__icontains=q
            )
            | Q(
                employee__phone_number__icontains=q
            )
            | Q(
                notes__icontains=q
            )
        )

    if shift_type_id.isdigit():
        queryset = queryset.filter(
            shift_type_id=int(shift_type_id)
        )

    if (
        rest_days
        and rest_days
        in dict(Break.RestDays.choices)
    ):
        queryset = queryset.filter(
            rest_days=rest_days
        )

    if (
        job_title
        and job_title
        in dict(Break.BreakJobTitle.choices)
    ):
        queryset = queryset.filter(
            job_title=job_title
        )

    if active_filter == "active":
        queryset = queryset.filter(
            is_active=True
        )

    elif active_filter == "inactive":
        queryset = queryset.filter(
            is_active=False
        )

    queryset = queryset.order_by(
        "shift_type__name",
        "rest_days",
        "employee__employee_number",
    )

    filters = {
        "q": q,
        "selected_shift_type": shift_type_id,
        "selected_rest_days": rest_days,
        "selected_job_title": job_title,
        "selected_active": active_filter,
    }

    return queryset, filters


# ==========================================================
# قائمة الراحات
# ==========================================================


@login_required
def breaks_list_view(
    request: HttpRequest,
) -> HttpResponse:
    require_staff(request.user)

    breaks, filters = _filtered_breaks_queryset(
        request
    )

    employees = (
        Employee.objects
        .filter(
            is_active=True,
        )
        .order_by(
            "employee_number",
        )
    )

    shift_types = (
        ShiftType.objects
        .all()
        .order_by(
            "name",
        )
    )

    all_breaks = Break.objects.all()
    active_employee_count = employees.count()
    employees_with_active_breaks = (
        all_breaks.filter(is_active=True)
        .values("employee").distinct().count()
    )
    employees_without_breaks = max(
        active_employee_count - employees_with_active_breaks,
        0,
    )
    break_coverage_rate = round(
        employees_with_active_breaks / active_employee_count * 100,
        1,
    ) if active_employee_count else 0

    shift_stats = (
        all_breaks
        .filter(
            is_active=True,
        )
        .values(
            "shift_type__name",
        )
        .annotate(
            total=Count("id"),
        )
        .order_by(
            "shift_type__name",
        )
    )

    recent_history = (
        BreakHistory.objects
        .select_related(
            "employee",
            "shift_type",
            "performed_by",
        )
        .order_by(
            "-created_at",
        )[:20]
    )

    context = {
        "breaks": breaks,
        "employees": employees,
        "shift_types": shift_types,
        "rest_days_choices": (
            Break.RestDays.choices
        ),
        "job_title_choices": (
            Break.BreakJobTitle.choices
        ),
        "total_breaks": (
            all_breaks.count()
        ),
        "active_breaks": (
            all_breaks
            .filter(
                is_active=True,
            )
            .count()
        ),
        "inactive_breaks": (
            all_breaks
            .filter(
                is_active=False,
            )
            .count()
        ),
        "employees_with_breaks": (
            employees_with_active_breaks
        ),
        "active_employee_count": active_employee_count,
        "employees_without_breaks": employees_without_breaks,
        "break_coverage_rate": break_coverage_rate,
        "shift_stats": shift_stats,
        "recent_break_history": recent_history,
        **filters,
    }

    return render(
        request,
        "breaks/breaks_list.html",
        context,
    )


# ==========================================================
# إضافة راحة
# ==========================================================


@login_required
@require_POST
def break_create_view(
    request: HttpRequest,
) -> HttpResponse:
    require_staff(request.user)

    employee_id = _post_value(
        request,
        "employee_id",
    )

    shift_type_id = _post_value(
        request,
        "shift_type_id",
    )

    job_title = _post_value(
        request,
        "job_title",
    )

    rest_days = _post_value(
        request,
        "rest_days",
    )

    notes = _post_value(
        request,
        "notes",
    )

    try:
        _validate_break_choices(
            job_title=job_title,
            rest_days=rest_days,
        )

        employee = _get_active_employee(
            employee_id
        )

        shift_type = _get_shift_type(
            shift_type_id
        )

        with transaction.atomic():
            # قفل سجلات الموظف في الوردية نفسها
            # لتقليل احتمالية الإنشاء المتزامن.
            (
                Break.objects
                .select_for_update()
                .filter(
                    employee=employee,
                    shift_type=shift_type,
                )
                .exists()
            )

            break_obj = Break(
                employee=employee,
                shift_type=shift_type,
                job_title=job_title,
                rest_days=rest_days,
                notes=notes,
                is_active=True,
            )

            break_obj.save()

            snapshot = break_obj.to_snapshot()

            _record_break_history(
                break_obj=break_obj,
                break_id_snapshot=break_obj.pk,
                employee=employee,
                shift_type=shift_type,
                action=BreakHistory.Action.CREATE,
                request=request,
                old_value={},
                new_value=snapshot,
                reason=(
                    "إنشاء راحة أسبوعية جديدة"
                ),
            )

            log_activity(
                user=request.user,
                module="الراحات",
                action=(
                    SystemActivityLog
                    .ActionType
                    .CREATE
                ),
                description=(
                    "تم إضافة راحة للموظف "
                    f"{employee.full_name} "
                    f"في وردية {shift_type.name}"
                ),
                request=request,
            )

            _schedule_notification(
                lambda: NotificationService.success(
                    title="تم إضافة راحة",
                    message=(
                        "تم إضافة راحة للموظف "
                        f"{employee.full_name}"
                    ),
                    user=request.user,
                    url="/breaks/",
                )
            )

        messages.success(
            request,
            (
                "تم إضافة راحة الموظف "
                f"{employee.full_name} بنجاح."
            ),
        )

    except IntegrityError:
        messages.error(
            request,
            (
                "هذا الموظف لديه راحة نشطة "
                "مسجلة مسبقًا في الوردية نفسها."
            ),
        )

    except ValidationError as error:
        messages.error(
            request,
            _first_validation_message(error),
        )

    return _redirect_to_breaks_list()


# ==========================================================
# تعديل راحة
# ==========================================================


@login_required
@require_POST
def break_update_view(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    require_staff(request.user)

    employee_id = _post_value(
        request,
        "employee_id",
    )

    shift_type_id = _post_value(
        request,
        "shift_type_id",
    )

    job_title = _post_value(
        request,
        "job_title",
    )

    rest_days = _post_value(
        request,
        "rest_days",
    )

    notes = _post_value(
        request,
        "notes",
    )

    reason = _post_value(
        request,
        "change_reason",
    )

    try:
        _validate_break_choices(
            job_title=job_title,
            rest_days=rest_days,
        )

        employee = _get_active_employee(
            employee_id
        )

        shift_type = _get_shift_type(
            shift_type_id
        )

        with transaction.atomic():
            break_obj = get_object_or_404(
                (
                    Break.objects
                    .select_for_update()
                    .select_related(
                        "employee",
                        "shift_type",
                    )
                ),
                pk=pk,
            )

            old_snapshot = (
                break_obj.to_snapshot()
            )

            break_obj.employee = employee
            break_obj.shift_type = shift_type
            break_obj.job_title = job_title
            break_obj.rest_days = rest_days
            break_obj.notes = notes

            break_obj.save()

            new_snapshot = (
                break_obj.to_snapshot()
            )

            if old_snapshot == new_snapshot:
                messages.info(
                    request,
                    "لم يتم إجراء أي تغيير على الراحة.",
                )

                return _redirect_to_breaks_list()

            _record_break_history(
                break_obj=break_obj,
                break_id_snapshot=break_obj.pk,
                employee=employee,
                shift_type=shift_type,
                action=BreakHistory.Action.UPDATE,
                request=request,
                old_value=old_snapshot,
                new_value=new_snapshot,
                reason=(
                    reason
                    or "تعديل بيانات الراحة الأسبوعية"
                ),
            )

            log_activity(
                user=request.user,
                module="الراحات",
                action=(
                    SystemActivityLog
                    .ActionType
                    .UPDATE
                ),
                description=(
                    "تم تعديل راحة الموظف "
                    f"{employee.full_name}"
                ),
                request=request,
            )

            _schedule_notification(
                lambda: NotificationService.info(
                    title="تم تعديل راحة",
                    message=(
                        "تم تعديل راحة الموظف "
                        f"{employee.full_name}"
                    ),
                    user=request.user,
                    url="/breaks/",
                )
            )

        messages.success(
            request,
            (
                "تم تعديل راحة الموظف "
                f"{employee.full_name} بنجاح."
            ),
        )

    except IntegrityError:
        messages.error(
            request,
            (
                "لا يمكن حفظ التعديل؛ الموظف لديه "
                "راحة نشطة أخرى في الوردية نفسها."
            ),
        )

    except ValidationError as error:
        messages.error(
            request,
            _first_validation_message(error),
        )

    return _redirect_to_breaks_list()


# ==========================================================
# تفعيل أو تعطيل راحة
# ==========================================================


@login_required
@require_POST
def break_toggle_active_view(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    require_staff(request.user)

    reason = _post_value(
        request,
        "change_reason",
    )

    try:
        with transaction.atomic():
            break_obj = get_object_or_404(
                (
                    Break.objects
                    .select_for_update()
                    .select_related(
                        "employee",
                        "shift_type",
                    )
                ),
                pk=pk,
            )

            old_snapshot = (
                break_obj.to_snapshot()
            )

            was_active = break_obj.is_active
            break_obj.is_active = not was_active

            break_obj.save(
                update_fields=[
                    "is_active",
                    "updated_at",
                ]
            )

            new_snapshot = (
                break_obj.to_snapshot()
            )

            if break_obj.is_active:
                history_action = (
                    BreakHistory.Action.ACTIVATE
                )
                action_text = "تفعيل"
                notification_method = (
                    NotificationService.success
                )
                message_level = "success"

            else:
                history_action = (
                    BreakHistory.Action.DEACTIVATE
                )
                action_text = "تعطيل"
                notification_method = (
                    NotificationService.warning
                )
                message_level = "warning"

            _record_break_history(
                break_obj=break_obj,
                break_id_snapshot=break_obj.pk,
                employee=break_obj.employee,
                shift_type=break_obj.shift_type,
                action=history_action,
                request=request,
                old_value=old_snapshot,
                new_value=new_snapshot,
                reason=(
                    reason
                    or f"{action_text} الراحة الأسبوعية"
                ),
            )

            log_activity(
                user=request.user,
                module="الراحات",
                action=(
                    SystemActivityLog
                    .ActionType
                    .UPDATE
                ),
                description=(
                    f"تم {action_text} راحة الموظف "
                    f"{break_obj.employee.full_name}"
                ),
                request=request,
            )

            employee_name = (
                break_obj.employee.full_name
            )

            _schedule_notification(
                lambda: notification_method(
                    title=f"تم {action_text} راحة",
                    message=(
                        f"تم {action_text} راحة الموظف "
                        f"{employee_name}"
                    ),
                    user=request.user,
                    url="/breaks/",
                )
            )

        if message_level == "success":
            messages.success(
                request,
                "تم تفعيل الراحة بنجاح.",
            )

        else:
            messages.warning(
                request,
                "تم تعطيل الراحة بنجاح.",
            )

    except IntegrityError:
        messages.error(
            request,
            (
                "تعذر تفعيل الراحة؛ توجد راحة نشطة "
                "أخرى للموظف في الوردية نفسها."
            ),
        )

    except ValidationError as error:
        messages.error(
            request,
            _first_validation_message(error),
        )

    return _redirect_to_breaks_list()


# ==========================================================
# حذف راحة
# ==========================================================


@login_required
@require_POST
def break_delete_view(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    require_staff(request.user)

    reason = _post_value(
        request,
        "delete_reason",
    )

    try:
        with transaction.atomic():
            break_obj = get_object_or_404(
                (
                    Break.objects
                    .select_for_update()
                    .select_related(
                        "employee",
                        "shift_type",
                    )
                ),
                pk=pk,
            )

            employee = break_obj.employee
            shift_type = break_obj.shift_type
            employee_name = employee.full_name
            break_id_snapshot = break_obj.pk

            old_snapshot = (
                break_obj.to_snapshot()
            )

            history = _record_break_history(
                break_obj=break_obj,
                break_id_snapshot=break_id_snapshot,
                employee=employee,
                shift_type=shift_type,
                action=BreakHistory.Action.DELETE,
                request=request,
                old_value=old_snapshot,
                new_value={
                    "deleted": True,
                },
                reason=(
                    reason
                    or "حذف سجل الراحة الأسبوعية"
                ),
            )

            break_obj.delete()

            # بعد الحذف يتحول FK إلى NULL بسبب SET_NULL.
            # هذه الخطوة صريحة للتأكد من عدم بقاء مرجع.
            if history.break_record_id is not None:
                history.break_record = None
                history.save(
                    update_fields=[
                        "break_record",
                    ]
                )

            log_activity(
                user=request.user,
                module="الراحات",
                action=(
                    SystemActivityLog
                    .ActionType
                    .DELETE
                ),
                description=(
                    "تم حذف راحة الموظف "
                    f"{employee_name}"
                ),
                request=request,
            )

            _schedule_notification(
                lambda: NotificationService.danger(
                    title="تم حذف راحة",
                    message=(
                        "تم حذف راحة الموظف "
                        f"{employee_name}"
                    ),
                    user=request.user,
                    url="/breaks/",
                )
            )

        messages.warning(
            request,
            (
                "تم حذف راحة الموظف "
                f"{employee_name}."
            ),
        )

    except ValidationError as error:
        messages.error(
            request,
            _first_validation_message(error),
        )

    except IntegrityError:
        messages.error(
            request,
            (
                "تعذر حذف الراحة بسبب ارتباطها "
                "بسجلات تشغيلية أخرى."
            ),
        )

    return _redirect_to_breaks_list()
