from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


# ==========================================================
# أدوات مساعدة
# ==========================================================

def _normalize_reason(
    reason: Any,
) -> str:
    """
    تنظيف سبب تغيير حالة البلاغ.
    """

    if reason is None:
        return ""

    return str(reason).strip()


def _normalize_closing_notes(
    closing_notes: Any,
) -> str:
    """
    تنظيف ملاحظات إغلاق البلاغ.
    """

    if closing_notes is None:
        return ""

    return str(closing_notes).strip()


def _validate_status(
    *,
    incident,
    new_status: str,
) -> str:
    """
    التحقق من أن حالة البلاغ الجديدة
    ضمن الحالات المسموحة في النموذج.
    """

    normalized_status = str(
        new_status or ""
    ).strip().lower()

    status_field = incident._meta.get_field(
        "status"
    )

    allowed_statuses = {
        value
        for value, _label
        in status_field.choices
    }

    if normalized_status not in allowed_statuses:
        raise ValidationError(
            {
                "status": (
                    "حالة البلاغ المطلوبة غير صحيحة."
                )
            }
        )

    return normalized_status


def _is_closed_status(
    status: str,
) -> bool:
    """
    هل الحالة تعتبر حالة نهائية للبلاغ؟
    """

    return status in {
        "closed",
        "resolved",
        "completed",
    }


def _serialize_value(
    value: Any,
) -> Any:
    """
    تحويل القيم إلى صيغة مناسبة للحفظ
    داخل السجل التاريخي.
    """

    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "pk"):
        return value.pk

    return value


def _get_effective_user(
    *,
    request=None,
    user=None,
):
    """
    تحديد المستخدم المنفذ للعملية.
    """

    if user is not None:
        if getattr(
            user,
            "is_authenticated",
            False,
        ):
            return user

        return None

    if request is None:
        return None

    request_user = getattr(
        request,
        "user",
        None,
    )

    if (
        request_user is not None
        and getattr(
            request_user,
            "is_authenticated",
            False,
        )
    ):
        return request_user

    return None


def _build_incident_snapshot(
    incident,
) -> dict[str, Any]:
    """
    إنشاء نسخة مختصرة من بيانات البلاغ.
    """

    snapshot = {
        "incident_id": incident.pk,
        "status": incident.status,
    }

    tracked_fields = [
        "incident_number",
        "shift_plan_id",
        "door_shift_id",
        "priority",
        "incident_type",
        "closed_by_id",
        "closed_at",
        "closing_notes",
        "updated_at",
    ]

    for field_name in tracked_fields:
        if not hasattr(
            incident,
            field_name,
        ):
            continue

        snapshot[field_name] = _serialize_value(
            getattr(
                incident,
                field_name,
            )
        )

    return snapshot


# ==========================================================
# تغيير حالة البلاغ
# ==========================================================

@transaction.atomic
def change_incident_status(
    *,
    incident,
    new_status: str,
    request=None,
    user=None,
    reason: str = "",
    closing_notes: str = "",
):
    """
    تغيير حالة البلاغ مع تسجيل القيم السابقة والجديدة.

    يعيد:
        tuple:
            updated_incident, changed
    """

    from apps.audit.services import (
        record_incident_status_history,
    )
    from apps.ops.models import Incident

    if incident is None:
        raise ValidationError(
            "البلاغ غير موجود."
        )

    if not getattr(
        incident,
        "pk",
        None,
    ):
        raise ValidationError(
            "البلاغ غير محفوظ."
        )

    locked_incident = (
        Incident.objects
        .select_for_update()
        .select_related(
            "shift_plan",
            "door_shift",
            "created_by",
            "closed_by",
        )
        .get(
            pk=incident.pk,
        )
    )

    normalized_status = _validate_status(
        incident=locked_incident,
        new_status=new_status,
    )

    old_status = locked_incident.status

    if old_status == normalized_status:
        return locked_incident, False

    clean_reason = _normalize_reason(
        reason
    )

    if not clean_reason:
        clean_reason = (
            "تحديث حالة البلاغ من لوحة العمليات"
        )

    clean_closing_notes = (
        _normalize_closing_notes(
            closing_notes
        )
    )

    effective_user = _get_effective_user(
        request=request,
        user=user,
    )

    if (
        normalized_status
        == Incident.Status.CLOSED
        and not clean_closing_notes
        and not str(
            locked_incident.closing_notes or ""
        ).strip()
    ):
        raise ValidationError(
            {
                "closing_notes": (
                    "ملاحظات الإغلاق مطلوبة."
                )
            }
        )

    old_snapshot = _build_incident_snapshot(
        locked_incident
    )

    locked_incident.status = normalized_status

    update_fields = [
        "status",
    ]

    if _is_closed_status(
        normalized_status
    ):
        locked_incident.closed_at = (
            timezone.now()
        )

        update_fields.append(
            "closed_at"
        )

        if effective_user is not None:
            locked_incident.closed_by = (
                effective_user
            )

            update_fields.append(
                "closed_by"
            )

        if clean_closing_notes:
            locked_incident.closing_notes = (
                clean_closing_notes
            )

            update_fields.append(
                "closing_notes"
            )

    else:
        locked_incident.closed_at = None
        locked_incident.closed_by = None

        update_fields.extend(
            [
                "closed_at",
                "closed_by",
            ]
        )

    locked_incident.full_clean()

    locked_incident.save(
        update_fields=list(
            dict.fromkeys(
                update_fields
            )
        )
    )

    locked_incident.refresh_from_db()

    new_snapshot = _build_incident_snapshot(
        locked_incident
    )

    record_incident_status_history(
        incident=locked_incident,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=effective_user,
        reason=clean_reason,
    )

    return locked_incident, True


# ==========================================================
# واجهة توافقية للـ Views
# ==========================================================

class IncidentService:
    """
    واجهة خدمة البلاغات المستخدمة في views.py.

    تدعم عدة أسماء متوقعة للدوال مع توجيهها
    إلى الدالة المركزية change_incident_status.
    """

    @staticmethod
    @transaction.atomic
    def create(
        *,
        request,
        active_shift,
        door_shift=None,
        assignment=None,
        section: str = "",
        description: str,
        incident_type: str,
        priority: str,
        reported_by_name: str = "",
        assigned_to_name: str = "",
    ):
        from apps.ops.models import Incident

        if not str(description or "").strip():
            raise ValidationError({
                "description": "وصف البلاغ مطلوب."
            })

        incident = Incident(
            shift_plan=active_shift,
            door_shift=door_shift,
            assignment=assignment,
            section=section,
            description=str(description).strip(),
            incident_type=incident_type,
            priority=priority,
            reported_by_name=str(
                reported_by_name or ""
            ).strip(),
            assigned_to_name=str(
                assigned_to_name or ""
            ).strip(),
            created_by=(
                request.user
                if getattr(
                    request.user,
                    "is_authenticated",
                    False,
                )
                else None
            ),
        )
        incident.full_clean()
        incident.save()
        return incident

    @staticmethod
    def change_status(
        *,
        incident,
        new_status: str,
        request=None,
        user=None,
        reason: str = "",
        closing_notes: str = "",
    ):
        return change_incident_status(
            incident=incident,
            new_status=new_status,
            request=request,
            user=user,
            reason=reason,
            closing_notes=closing_notes,
        )

    @staticmethod
    def change_incident_status(
        *,
        incident,
        new_status: str,
        request=None,
        user=None,
        reason: str = "",
        closing_notes: str = "",
    ):
        return change_incident_status(
            incident=incident,
            new_status=new_status,
            request=request,
            user=user,
            reason=reason,
            closing_notes=closing_notes,
        )

    @staticmethod
    def update_status(
        *,
        incident,
        new_status: str,
        request=None,
        user=None,
        reason: str = "",
        closing_notes: str = "",
    ):
        return change_incident_status(
            incident=incident,
            new_status=new_status,
            request=request,
            user=user,
            reason=reason,
            closing_notes=closing_notes,
        )

    @staticmethod
    def close_incident(
        *,
        incident,
        request=None,
        user=None,
        reason: str = "",
        closing_notes: str = "",
    ):
        from apps.ops.models import Incident

        return change_incident_status(
            incident=incident,
            new_status=Incident.Status.CLOSED,
            request=request,
            user=user,
            reason=(
                reason
                or "إغلاق البلاغ التشغيلي"
            ),
            closing_notes=closing_notes,
        )

    @staticmethod
    def resolve_incident(
        *,
        incident,
        request=None,
        user=None,
        reason: str = "",
        closing_notes: str = "",
    ):
        from apps.ops.models import Incident

        return change_incident_status(
            incident=incident,
            new_status=Incident.Status.RESOLVED,
            request=request,
            user=user,
            reason=(
                reason
                or "تم حل البلاغ التشغيلي"
            ),
            closing_notes=closing_notes,
        )

    @staticmethod
    def reopen_incident(
        *,
        incident,
        request=None,
        user=None,
        reason: str = "",
    ):
        from apps.ops.models import Incident

        return change_incident_status(
            incident=incident,
            new_status=Incident.Status.IN_PROGRESS,
            request=request,
            user=user,
            reason=(
                reason
                or "إعادة فتح البلاغ التشغيلي"
            ),
        )