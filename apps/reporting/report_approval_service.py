from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


VALID_ACTIONS = {
    "submitted",
    "approved",
    "rejected",
    "returned",
    "revoked",
}


def _serialize(value: Any) -> Any:
    """
    تحويل القيم إلى صيغة مناسبة للحفظ داخل JSONField.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "pk"):
        return {
            "id": value.pk,
            "label": str(value),
        }

    if isinstance(value, dict):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _serialize(item)
            for item in value
        ]

    return str(value)


def report_snapshot(
    report,
) -> dict[str, Any]:
    """
    أخذ نسخة تاريخية من بيانات التقرير.
    """

    if report is None:
        return {}

    snapshot = {
        "report_id": report.pk,
    }

    candidate_fields = [
        "report_number",
        "shift_plan_id",
        "status",
        "summary",
        "recommendations",
        "snapshot_data",
        "created_by_id",
        "approved_by_id",
        "created_at",
        "approved_at",
        "updated_at",
    ]

    for field_name in candidate_fields:
        if not hasattr(
            report,
            field_name,
        ):
            continue

        try:
            value = getattr(
                report,
                field_name,
            )
        except Exception:
            continue

        snapshot[field_name] = _serialize(
            value
        )

    return snapshot


def _resolve_user(
    *,
    request=None,
    user=None,
):
    """
    تحديد المستخدم المنفذ للعملية.
    """

    if user is not None:
        return user

    if request is None:
        return None

    request_user = getattr(
        request,
        "user",
        None,
    )

    if request_user is None:
        return None

    if not request_user.is_authenticated:
        return None

    return request_user


def _status_for_action(
    action: str,
) -> str | None:
    """
    ربط إجراء الاعتماد بحالة التقرير.

    الحالات المتوافقة مع ShiftReport:
    draft
    final
    approved
    """

    mapping = {
        "submitted": "final",
        "approved": "approved",
        "rejected": "draft",
        "returned": "draft",
        "revoked": "final",
    }

    return mapping.get(action)


def _validate_action(
    action: str,
) -> str:
    """
    التحقق من صحة إجراء الاعتماد.
    """

    normalized_action = str(
        action or ""
    ).strip().lower()

    if normalized_action not in VALID_ACTIONS:
        raise ValidationError(
            {
                "action": (
                    "إجراء اعتماد التقرير غير صحيح."
                )
            }
        )

    return normalized_action


def _validate_target_status(
    *,
    report,
    target_status: str,
) -> None:
    """
    التحقق من أن حالة التقرير المطلوبة موجودة
    ضمن خيارات حقل status.
    """

    status_field = report._meta.get_field(
        "status"
    )

    allowed_statuses = {
        value
        for value, _label
        in status_field.choices
    }

    if target_status not in allowed_statuses:
        raise ValidationError(
            {
                "status": (
                    f"حالة التقرير {target_status} "
                    "غير موجودة ضمن الخيارات المتاحة."
                )
            }
        )


@transaction.atomic
def change_report_approval(
    *,
    report,
    action: str,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تنفيذ إجراء اعتماد تقرير مع حفظ سجل تاريخي.

    الإجراءات المتاحة:
        submitted:
            رفع التقرير للاعتماد.

        approved:
            اعتماد التقرير.

        rejected:
            رفض التقرير وإعادته إلى مسودة.

        returned:
            إعادة التقرير للمراجعة.

        revoked:
            سحب الاعتماد وإعادته إلى الحالة النهائية.

    Returns:
        tuple:
            updated_report, changed
    """

    from apps.audit.services import (
        record_report_approval_history,
    )
    from apps.reporting.models import (
        ShiftReport,
    )

    if report is None:
        raise ValidationError(
            "التقرير غير موجود."
        )

    if not getattr(
        report,
        "pk",
        None,
    ):
        raise ValidationError(
            "التقرير غير محفوظ."
        )

    normalized_action = _validate_action(
        action
    )

    locked_report = (
        ShiftReport.objects
        .select_for_update()
        .select_related(
            "shift_plan",
            "created_by",
            "approved_by",
        )
        .get(
            pk=report.pk,
        )
    )

    old_snapshot = report_snapshot(
        locked_report
    )

    effective_user = _resolve_user(
        request=request,
        user=user,
    )

    target_status = _status_for_action(
        normalized_action
    )

    if target_status is None:
        raise ValidationError(
            "تعذر تحديد حالة التقرير المطلوبة."
        )

    _validate_target_status(
        report=locked_report,
        target_status=target_status,
    )

    old_status = locked_report.status

    update_fields = []

    if old_status != target_status:
        locked_report.status = target_status
        update_fields.append(
            "status"
        )

    if normalized_action == "approved":
        if effective_user is None:
            raise ValidationError(
                "يجب تحديد المستخدم الذي اعتمد التقرير."
            )

        if hasattr(
            locked_report,
            "approved_by",
        ):
            if (
                locked_report.approved_by_id
                != effective_user.pk
            ):
                locked_report.approved_by = (
                    effective_user
                )
                update_fields.append(
                    "approved_by"
                )

        if hasattr(
            locked_report,
            "approved_at",
        ):
            locked_report.approved_at = (
                timezone.now()
            )
            update_fields.append(
                "approved_at"
            )

    elif normalized_action in {
        "rejected",
        "returned",
        "revoked",
    }:
        if hasattr(
            locked_report,
            "approved_by",
        ):
            if locked_report.approved_by_id is not None:
                locked_report.approved_by = None
                update_fields.append(
                    "approved_by"
                )

        if hasattr(
            locked_report,
            "approved_at",
        ):
            if locked_report.approved_at is not None:
                locked_report.approved_at = None
                update_fields.append(
                    "approved_at"
                )

    update_fields = list(
        dict.fromkeys(
            update_fields
        )
    )

    default_reasons = {
        "submitted": "رفع التقرير للاعتماد",
        "approved": "اعتماد التقرير",
        "rejected": "رفض التقرير",
        "returned": "إعادة التقرير للمراجعة",
        "revoked": "سحب اعتماد التقرير",
    }

    clean_reason = str(
        reason
        or default_reasons[
            normalized_action
        ]
    ).strip()

    if not update_fields:
        return locked_report, False

    locked_report.full_clean()

    locked_report.save(
        update_fields=update_fields,
    )

    new_snapshot = report_snapshot(
        locked_report
    )

    record_report_approval_history(
        report=locked_report,
        action=normalized_action,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=effective_user,
        reason=clean_reason,
    )

    return locked_report, True