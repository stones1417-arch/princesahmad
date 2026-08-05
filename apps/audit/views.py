from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from apps.audit.models import (
    AssignmentHistory,
    DoorStateHistory,
    IncidentStatusHistory,
    MaintenanceStatusHistory,
    ReportApprovalHistory,
    ShiftPlanHistory,
)
from apps.core.permissions import require_staff


@dataclass(frozen=True)
class AuditModelDefinition:
    """
    تعريف نوع سجل التدقيق المستخدم في القائمة والتفاصيل.
    """

    key: str
    label: str
    icon: str
    model: type
    related_fields: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()


AUDIT_MODEL_REGISTRY: dict[str, AuditModelDefinition] = {
    "door_state": AuditModelDefinition(
        key="door_state",
        label="حالات الأبواب",
        icon="🚪",
        model=DoorStateHistory,
        related_fields=(
            "door_shift",
            "door_shift__shift_plan",
            "changed_by",
        ),
        search_fields=(
            "door_shift__door_number",
            "change_reason",
            "changed_by__username",
            "changed_by__first_name",
            "changed_by__last_name",
            "ip_address",
        ),
    ),
    "assignment": AuditModelDefinition(
        key="assignment",
        label="التوزيعات",
        icon="👥",
        model=AssignmentHistory,
        related_fields=(
            "assignment",
            "employee",
            "door",
            "shift_plan",
            "changed_by",
        ),
        search_fields=(
            "employee__full_name",
            "employee__employee_number",
            "door__name",
            "door__door_number",
            "change_reason",
            "changed_by__username",
            "ip_address",
        ),
    ),
    "maintenance": AuditModelDefinition(
        key="maintenance",
        label="الصيانة",
        icon="🛠️",
        model=MaintenanceStatusHistory,
        related_fields=(
            "maintenance_request",
            "changed_by",
        ),
        search_fields=(
            "maintenance_request__request_number",
            "maintenance_request__description",
            "change_reason",
            "changed_by__username",
            "ip_address",
        ),
    ),
    "incident": AuditModelDefinition(
        key="incident",
        label="البلاغات",
        icon="🚨",
        model=IncidentStatusHistory,
        related_fields=(
            "incident",
            "changed_by",
        ),
        search_fields=(
            "incident__incident_number",
            "incident__description",
            "change_reason",
            "changed_by__username",
            "ip_address",
        ),
    ),
    "shift_plan": AuditModelDefinition(
        key="shift_plan",
        label="الورديات",
        icon="🕒",
        model=ShiftPlanHistory,
        related_fields=(
            "shift_plan",
            "shift_plan__shift_type",
            "changed_by",
        ),
        search_fields=(
            "shift_plan__shift_type__name",
            "change_reason",
            "changed_by__username",
            "ip_address",
        ),
    ),
    "report_approval": AuditModelDefinition(
        key="report_approval",
        label="اعتماد التقارير",
        icon="📊",
        model=ReportApprovalHistory,
        related_fields=(
            "report",
            "changed_by",
        ),
        search_fields=(
            "report__report_number",
            "change_reason",
            "changed_by__username",
            "ip_address",
        ),
    ),
}


def _ensure_audit_access(
    request: HttpRequest,
) -> None:
    """
    التحقق من صلاحية الوصول إلى سجل التدقيق.
    """

    require_staff(request.user)

    if request.user.is_superuser:
        return

    permission_names = {
        "audit.view_doorstatehistory",
        "audit.view_assignmenthistory",
        "audit.view_maintenancestatushistory",
        "audit.view_incidentstatushistory",
        "audit.view_shiftplanhistory",
        "audit.view_reportapprovalhistory",
    }

    if not any(
        request.user.has_perm(permission_name)
        for permission_name in permission_names
    ):
        raise PermissionDenied(
            "ليس لديك صلاحية عرض سجل المراجعة."
        )


def _clean_get_value(
    request: HttpRequest,
    name: str,
) -> str:
    return str(
        request.GET.get(name) or ""
    ).strip()


def _get_definition(
    model_type: str,
) -> AuditModelDefinition:
    """
    جلب تعريف نوع السجل أو رفع 404.
    """

    definition = AUDIT_MODEL_REGISTRY.get(
        model_type
    )

    if definition is None:
        raise Http404(
            "نوع سجل التدقيق المطلوب غير موجود."
        )

    return definition


def _get_base_queryset(
    definition: AuditModelDefinition,
) -> QuerySet:
    """
    إنشاء QuerySet محسّن لنوع سجل التدقيق.
    """

    queryset = definition.model.objects.all()

    if definition.related_fields:
        queryset = queryset.select_related(
            *definition.related_fields
        )

    return queryset


def _build_search_query(
    definition: AuditModelDefinition,
    query: str,
) -> Q:
    """
    إنشاء استعلام بحث عام عبر حقول النوع المحدد.
    """

    search_query = Q()

    for field_name in definition.search_fields:
        search_query |= Q(
            **{
                f"{field_name}__icontains": query
            }
        )

    return search_query


def _get_changed_by_name(
    record: Any,
) -> str:
    user = getattr(
        record,
        "changed_by",
        None,
    )

    if user is None:
        return "عملية نظامية"

    full_name = str(
        user.get_full_name() or ""
    ).strip()

    return (
        full_name
        or user.username
        or "مستخدم النظام"
    )


def _get_record_title(
    model_type: str,
    record: Any,
) -> str:
    """
    العنوان الرئيسي للسجل.
    """

    if model_type == "door_state":
        return (
            f"الباب رقم "
            f"{record.door_shift.door_number}"
        )

    if model_type == "assignment":
        if record.employee_id:
            return record.employee.full_name

        return f"سجل توزيع رقم {record.pk}"

    if model_type == "maintenance":
        request_number = getattr(
            record.maintenance_request,
            "request_number",
            "",
        )

        return (
            request_number
            or f"طلب صيانة رقم "
            f"{record.maintenance_request_id}"
        )

    if model_type == "incident":
        incident_number = getattr(
            record.incident,
            "incident_number",
            "",
        )

        return (
            incident_number
            or f"بلاغ رقم {record.incident_id}"
        )

    if model_type == "shift_plan":
        return str(record.shift_plan)

    if model_type == "report_approval":
        return (
            record.report.report_number
            or f"تقرير رقم {record.report_id}"
        )

    return str(record)


def _get_record_action(
    model_type: str,
    record: Any,
) -> str:
    """
    اسم الإجراء الظاهر.
    """

    if hasattr(record, "get_action_display"):
        return record.get_action_display()

    old_value = record.old_value or {}
    new_value = record.new_value or {}

    old_status = (
        old_value.get("status")
        or old_value.get("state")
        or "—"
    )

    new_status = (
        new_value.get("status")
        or new_value.get("state")
        or "—"
    )

    if old_status == "—" and new_status == "—":
        return "تحديث سجل"

    return f"{old_status} ← {new_status}"


def _serialize_record(
    model_type: str,
    definition: AuditModelDefinition,
    record: Any,
) -> dict[str, Any]:
    """
    تجهيز السجل للعرض الموحد داخل القالب.
    """

    return {
        "id": record.pk,
        "model_type": model_type,
        "type_label": definition.label,
        "type_icon": definition.icon,
        "title": _get_record_title(
            model_type,
            record,
        ),
        "action": _get_record_action(
            model_type,
            record,
        ),
        "reason": (
            record.change_reason
            or "لا يوجد سبب مسجل"
        ),
        "changed_by_name": (
            _get_changed_by_name(record)
        ),
        "changed_at": record.changed_at,
        "ip_address": (
            record.ip_address
            or "—"
        ),
        "old_value": record.old_value or {},
        "new_value": record.new_value or {},
        "object": record,
    }


def _apply_filters(
    request: HttpRequest,
    definition: AuditModelDefinition,
    queryset: QuerySet,
) -> QuerySet:
    """
    تطبيق فلاتر البحث والتاريخ والمستخدم.
    """

    query = _clean_get_value(
        request,
        "q",
    )

    user_id = _clean_get_value(
        request,
        "user",
    )

    date_from_value = _clean_get_value(
        request,
        "date_from",
    )

    date_to_value = _clean_get_value(
        request,
        "date_to",
    )

    if query:
        queryset = queryset.filter(
            _build_search_query(
                definition,
                query,
            )
        )

    if user_id.isdigit():
        queryset = queryset.filter(
            changed_by_id=int(user_id)
        )

    date_from = parse_date(
        date_from_value
    )

    if date_from:
        queryset = queryset.filter(
            changed_at__date__gte=date_from
        )

    date_to = parse_date(
        date_to_value
    )

    if date_to:
        queryset = queryset.filter(
            changed_at__date__lte=date_to
        )

    return queryset


@login_required
@require_GET
def history_list_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    عرض قائمة موحدة لجميع سجلات التدقيق.
    """

    _ensure_audit_access(
        request
    )

    selected_type = _clean_get_value(
        request,
        "type",
    )

    query = _clean_get_value(
        request,
        "q",
    )

    selected_user = _clean_get_value(
        request,
        "user",
    )

    date_from = _clean_get_value(
        request,
        "date_from",
    )

    date_to = _clean_get_value(
        request,
        "date_to",
    )

    records: list[dict[str, Any]] = []

    definitions = AUDIT_MODEL_REGISTRY

    if selected_type:
        definitions = {
            selected_type: _get_definition(
                selected_type
            )
        }

    for model_type, definition in definitions.items():
        queryset = _get_base_queryset(
            definition
        )

        queryset = _apply_filters(
            request,
            definition,
            queryset,
        )

        for record in queryset[:500]:
            records.append(
                _serialize_record(
                    model_type,
                    definition,
                    record,
                )
            )

    records.sort(
        key=lambda item: item["changed_at"],
        reverse=True,
    )

    records = records[:500]

    from django.contrib.auth import get_user_model

    User = get_user_model()

    users = (
        User.objects
        .filter(
            is_active=True,
        )
        .order_by(
            "username",
        )
    )

    type_counts = {}

    total_records = 0

    for model_type, definition in (
        AUDIT_MODEL_REGISTRY.items()
    ):
        count = (
            definition.model.objects.count()
        )

        type_counts[model_type] = count
        total_records += count

    context = {
        "page_title": "سجل المراجعة والتدقيق",
        "records": records,
        "audit_types": (
            AUDIT_MODEL_REGISTRY.values()
        ),
        "type_counts": type_counts,
        "total_records": total_records,
        "visible_records_count": len(records),
        "users": users,
        "selected_type": selected_type,
        "selected_user": selected_user,
        "q": query,
        "date_from": date_from,
        "date_to": date_to,
    }

    return render(
        request,
        "audit/history_list.html",
        context,
    )


@login_required
@require_GET
def history_detail_view(
    request: HttpRequest,
    model_type: str,
    pk: int,
) -> HttpResponse:
    """
    عرض التفاصيل الكاملة لسجل تدقيق واحد.
    """

    _ensure_audit_access(
        request
    )

    definition = _get_definition(
        model_type
    )

    queryset = _get_base_queryset(
        definition
    )

    try:
        record = queryset.get(
            pk=pk
        )

    except definition.model.DoesNotExist as exc:
        raise Http404(
            "سجل التدقيق المطلوب غير موجود."
        ) from exc

    serialized_record = _serialize_record(
        model_type,
        definition,
        record,
    )

    old_items = list(
        serialized_record[
            "old_value"
        ].items()
    )

    new_items = list(
        serialized_record[
            "new_value"
        ].items()
    )

    all_keys = sorted(
        set(
            serialized_record[
                "old_value"
            ].keys()
        )
        | set(
            serialized_record[
                "new_value"
            ].keys()
        )
    )

    changes = []

    for key in all_keys:
        old_value = serialized_record[
            "old_value"
        ].get(
            key,
            "—",
        )

        new_value = serialized_record[
            "new_value"
        ].get(
            key,
            "—",
        )

        changes.append(
            {
                "field": key,
                "old_value": old_value,
                "new_value": new_value,
                "changed": (
                    old_value != new_value
                ),
            }
        )

    context = {
        "page_title": (
            f"تفاصيل سجل: "
            f"{serialized_record['title']}"
        ),
        "record": serialized_record,
        "history_object": record,
        "definition": definition,
        "old_items": old_items,
        "new_items": new_items,
        "changes": changes,
    }

    return render(
        request,
        "audit/history_detail.html",
        context,
    )