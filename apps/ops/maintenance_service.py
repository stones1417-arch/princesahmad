from __future__ import annotations

from typing import Any
import re

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
    تنظيف سبب تغيير الحالة.
    """

    if reason is None:
        return ""

    return str(reason).strip()


def normalize_saudi_mobile(value: str) -> str:
    """Validate and normalize a Saudi mobile number without sending messages."""
    raw = re.sub(r"[\s\-()]", "", str(value or "").strip())
    if not raw:
        return ""
    if raw.startswith("+966"):
        raw = "0" + raw[4:]
    elif raw.startswith("966"):
        raw = "0" + raw[3:]
    if not re.fullmatch(r"05\d{8}", raw):
        raise ValidationError({"technician_phone": "رقم جوال الفني يجب أن يكون رقمًا سعوديًا صحيحًا."})
    return raw


def _validate_status(
    *,
    maintenance_request,
    new_status: str,
) -> str:
    """
    التحقق من أن حالة الصيانة الجديدة
    موجودة ضمن الخيارات الرسمية للنموذج.
    """

    normalized_status = str(
        new_status or ""
    ).strip().lower()

    status_field = (
        maintenance_request
        ._meta
        .get_field("status")
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
                    "حالة طلب الصيانة المطلوبة "
                    "غير صحيحة."
                )
            }
        )

    return normalized_status


def _serialize_value(
    value: Any,
):
    """
    تحويل القيم الزمنية إلى صيغة مناسبة
    للحفظ داخل JSONField.
    """

    if hasattr(
        value,
        "isoformat",
    ):
        return value.isoformat()

    return value


def _get_authenticated_user(
    *,
    request=None,
    user=None,
):
    """
    تحديد المستخدم المنفذ للعملية.

    المستخدم المرسل مباشرة له الأولوية،
    ثم مستخدم الطلب إذا كان مسجلًا.
    """

    if (
        user is not None
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    ):
        return user

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


def _build_maintenance_snapshot(
    maintenance_request,
) -> dict[str, Any]:
    """
    إنشاء لقطة كاملة لحالة طلب الصيانة.

    تتضمن أوقات انتقال الحالة حتى يمكن
    التحقق منها داخل سجل التدقيق.
    """

    snapshot_fields = [
        "door_shift_id",
        "shift_plan_id",
        "assigned_to_id",
        "created_by_id",
        "approved_by_id",
        "closed_by_id",
        "technician_name",
        "priority",
        "approved_at",
        "started_at",
        "fixed_at",
        "completed_at",
        "closed_at",
        "created_at",
        "updated_at",
        "notes",
        "closing_notes",
        "description",
        "rating",
    ]

    snapshot: dict[str, Any] = {
        "maintenance_request_id": (
            maintenance_request.pk
        ),
        "request_number": getattr(
            maintenance_request,
            "request_number",
            "",
        ),
        "status": maintenance_request.status,
    }

    for field_name in snapshot_fields:
        if not hasattr(
            maintenance_request,
            field_name,
        ):
            continue

        snapshot[field_name] = (
            _serialize_value(
                getattr(
                    maintenance_request,
                    field_name,
                )
            )
        )

    return snapshot


# ==========================================================
# الخدمة المركزية لتغيير حالة الصيانة
# ==========================================================


@transaction.atomic
def change_maintenance_status(
    *,
    maintenance_request,
    new_status: str,
    request=None,
    user=None,
    reason: str = "",
):
    """
    تحديث حالة طلب الصيانة وتسجيل سجل تدقيق.

    تعتمد هذه الدالة على save() الكامل للنموذج،
    حتى تعمل قواعد MaintenanceRequest وتُحفظ
    أوقات انتقال الحالة، مثل:

    - approved_at
    - started_at
    - fixed_at
    - completed_at
    - closed_at

    Returns:
        tuple:
            updated_maintenance_request, changed
    """

    from apps.audit.services import (
        record_maintenance_status_history,
    )
    from apps.ops.models import (
        MaintenanceRequest,
    )

    if maintenance_request is None:
        raise ValidationError(
            "طلب الصيانة غير موجود."
        )

    if not getattr(
        maintenance_request,
        "pk",
        None,
    ):
        raise ValidationError(
            "طلب الصيانة غير محفوظ."
        )

    locked_request = (
        MaintenanceRequest.objects
        .select_for_update()
        .get(
            pk=maintenance_request.pk,
        )
    )

    normalized_status = _validate_status(
        maintenance_request=locked_request,
        new_status=new_status,
    )

    old_status = locked_request.status

    if old_status == normalized_status:
        return locked_request, False

    clean_reason = _normalize_reason(
        reason
    )

    if not clean_reason:
        clean_reason = (
            "تحديث حالة طلب الصيانة "
            "من لوحة العمليات"
        )

    effective_user = _get_authenticated_user(
        request=request,
        user=user,
    )

    old_snapshot = (
        _build_maintenance_snapshot(
            locked_request
        )
    )

    locked_request.status = normalized_status

    # مهم:
    # لا تستخدم update_fields=["status"] هنا.
    # نموذج MaintenanceRequest يضبط أوقات انتقال
    # الحالة داخل save()، والحفظ الجزئي سيمنع
    # حفظ started_at وfixed_at وclosed_at وغيرها.
    locked_request.save()

    # تحميل القيم النهائية التي ضبطها النموذج
    # أثناء الحفظ.
    locked_request.refresh_from_db()

    new_snapshot = (
        _build_maintenance_snapshot(
            locked_request
        )
    )

    record_maintenance_status_history(
        maintenance_request=locked_request,
        old_value=old_snapshot,
        new_value=new_snapshot,
        request=request,
        user=effective_user,
        reason=clean_reason,
    )

    return locked_request, True


# ==========================================================
# واجهة خدمة الصيانة المستخدمة داخل views.py
# ==========================================================


class MaintenanceService:
    """
    واجهة موحدة لإنشاء طلبات الصيانة
    وتحديث حالاتها.

    متوافقة مع الاستدعاءات الموجودة داخل:

        apps/ops/views.py
    """

    @staticmethod
    @transaction.atomic
    def create_request(
        *,
        request,
        door,
        description: str,
        priority: str,
        technician_name: str = "",
        technician_phone: str = "",
        planned_start_at=None,
        planned_end_at=None,
        section: str = "",
        assignment=None,
        source_incident=None,
    ):
        """
        إنشاء طلب صيانة جديد بانتظار مراجعة مركز العمليات.
        """

        from apps.ops.models import (
            DoorShift,
            MaintenanceRequest,
        )

        if door is None:
            raise ValidationError(
                {
                    "door": (
                        "سجل الباب غير موجود."
                    )
                }
            )

        if not getattr(
            door,
            "pk",
            None,
        ):
            raise ValidationError(
                {
                    "door": (
                        "سجل الباب غير محفوظ."
                    )
                }
            )

        locked_door = (
            DoorShift.objects
            .select_for_update()
            .get(
                pk=door.pk,
            )
        )

        if not locked_door.is_active:
            raise ValidationError(
                {
                    "door": (
                        "الباب غير نشط."
                    )
                }
            )

        if not locked_door.shift_plan.is_active:
            raise ValidationError(
                {
                    "door": (
                        "لا يمكن إنشاء طلب صيانة "
                        "لباب تابع لوردية غير نشطة."
                    )
                }
            )

        clean_description = str(
            description or ""
        ).strip()

        active_statuses = {
            MaintenanceRequest.Status.NEW,
            MaintenanceRequest.Status.APPROVED,
            MaintenanceRequest.Status.ASSIGNED,
            MaintenanceRequest.Status.IN_PROGRESS,
            MaintenanceRequest.Status.OPEN,
        }
        existing_request = (
            MaintenanceRequest.objects
            .select_for_update()
            .filter(
                door_shift=locked_door,
                status__in=active_statuses,
            )
            .order_by("-created_at")
            .first()
        )
        if existing_request is not None:
            raise ValidationError(
                {
                    "door": (
                        "يوجد طلب صيانة نشط لهذا الباب بالفعل: "
                        f"{existing_request.request_number}"
                    )
                }
            )

        if not clean_description:
            raise ValidationError(
                {
                    "description": (
                        "وصف مشكلة الصيانة مطلوب."
                    )
                }
            )

        normalized_priority = str(
            priority or ""
        ).strip().lower()

        valid_priorities = {
            value
            for value, _label
            in MaintenanceRequest.Priority.choices
        }

        if (
            normalized_priority
            not in valid_priorities
        ):
            raise ValidationError(
                {
                    "priority": (
                        "درجة أولوية طلب الصيانة "
                        "غير صحيحة."
                    )
                }
            )

        clean_technician_name = str(
            technician_name or ""
        ).strip()

        if not planned_start_at or not planned_end_at:
            raise ValidationError({
                "planned_start_at": "وقت البدء والانتهاء المخططان مطلوبان للطلبات الجديدة."
            })
        if timezone.is_naive(planned_start_at) or timezone.is_naive(planned_end_at):
            raise ValidationError({
                "planned_start_at": "يجب أن تكون أوقات الخطة مرتبطة بالمنطقة الزمنية."
            })
        if planned_end_at <= planned_start_at:
            raise ValidationError({
                "planned_end_at": "يجب أن يكون وقت الانتهاء المخطط بعد وقت البدء المخطط."
            })

        clean_technician_phone = normalize_saudi_mobile(technician_phone)
        if clean_technician_phone and not clean_technician_name:
            raise ValidationError({
                "technician_name": "اسم الفني مطلوب عند إدخال رقم الجوال."
            })

        created_by = (
            _get_authenticated_user(
                request=request,
            )
        )

        maintenance = MaintenanceRequest(
            door_shift=locked_door,
            assignment=assignment,
            section=section,
            description=clean_description,
            priority=normalized_priority,
            status=(
                MaintenanceRequest
                .Status
                .NEW
            ),
            technician_name=(
                clean_technician_name
            ),
            technician_phone=clean_technician_phone,
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            created_by=created_by,
            source_incident=source_incident,
        )

        maintenance.full_clean()
        maintenance.save()

        from apps.notifications.models import Notification
        from apps.scheduling.models import ShiftOperationalLeadership
        from apps.scheduling.operational_leadership_service import resolve_shift_leader

        operations_leader = resolve_shift_leader(
            locked_door.shift_plan,
            ShiftOperationalLeadership.Responsibility.OPERATIONS_SUPERVISOR,
        )
        if operations_leader:
            Notification.objects.create(
                user=operations_leader,
                title="طلب صيانة جديد للمراجعة",
                message=f"الطلب {maintenance.request_number} ينتظر المراجعة التشغيلية.",
                section=maintenance.section,
                url="/ops/maintenance/",
            )

        return maintenance

    @staticmethod
    @transaction.atomic
    def update_status(
        *,
        request,
        maintenance,
        new_status: str,
        closing_notes: str = "",
        reason: str = "",
        user=None,
    ):
        """
        تحديث حالة طلب الصيانة.

        عند إنهاء طلب الصيانة:
        - يتحقق من وجود ملاحظات الإغلاق.
        - يعيد الباب إلى الحالة المفتوحة.
        - يسجل انتقالات الحالة في Audit.

        Returns:
            MaintenanceRequest
        """

        from apps.ops.door_service import (
            change_door_state,
        )
        from apps.ops.models import (
            DoorShift,
            MaintenanceRequest,
        )

        if maintenance is None:
            raise ValidationError(
                "طلب الصيانة غير موجود."
            )

        if not getattr(
            maintenance,
            "pk",
            None,
        ):
            raise ValidationError(
                "طلب الصيانة غير محفوظ."
            )

        maintenance = (
            MaintenanceRequest.objects
            .select_for_update()
            .get(
                pk=maintenance.pk,
            )
        )

        clean_closing_notes = str(
            closing_notes or ""
        ).strip()

        normalized_status = _validate_status(
            maintenance_request=maintenance,
            new_status=new_status,
        )

        allowed_transitions = {
            MaintenanceRequest.Status.NEW: {
                MaintenanceRequest.Status.APPROVED,
                MaintenanceRequest.Status.CLOSED,
            },
            MaintenanceRequest.Status.APPROVED: {
                MaintenanceRequest.Status.ASSIGNED,
                MaintenanceRequest.Status.IN_PROGRESS,
            },
            MaintenanceRequest.Status.ASSIGNED: {
                MaintenanceRequest.Status.IN_PROGRESS,
            },
            MaintenanceRequest.Status.IN_PROGRESS: {
                MaintenanceRequest.Status.FIXED,
                MaintenanceRequest.Status.DONE,
            },
            MaintenanceRequest.Status.FIXED: {
                MaintenanceRequest.Status.DONE,
            },
        }
        if (
            normalized_status != maintenance.status
            and normalized_status not in allowed_transitions.get(
                maintenance.status, set()
            )
        ):
            raise ValidationError(
                {"status": "انتقال حالة طلب الصيانة غير مسموح."}
            )

        final_statuses = {
            MaintenanceRequest.Status.CLOSED,
        }

        # دعم DONE فقط إذا كانت موجودة فعليًا
        # ضمن نموذج MaintenanceRequest.
        done_status = getattr(
            MaintenanceRequest.Status,
            "DONE",
            None,
        )

        if done_status:
            final_statuses.add(
                done_status
            )

        existing_closing_notes = str(
            getattr(
                maintenance,
                "closing_notes",
                "",
            )
            or ""
        ).strip()

        if (
            normalized_status in final_statuses
            and not clean_closing_notes
            and not existing_closing_notes
        ):
            raise ValidationError(
                {
                    "closing_notes": (
                        "ملاحظات الإغلاق مطلوبة."
                    )
                }
            )

        if clean_closing_notes:
            maintenance.closing_notes = (
                clean_closing_notes
            )

            # الحفظ الكامل أكثر أمانًا هنا،
            # خصوصًا إذا كان النموذج يطبق قواعد
            # إضافية داخل save().
            maintenance.save()

            maintenance.refresh_from_db()

        effective_user = (
            _get_authenticated_user(
                request=request,
                user=user,
            )
        )

        if normalized_status == MaintenanceRequest.Status.APPROVED:
            maintenance.approved_by = effective_user
            maintenance.save()
            maintenance.refresh_from_db()

        updated_maintenance, changed = (
            change_maintenance_status(
                maintenance_request=maintenance,
                new_status=normalized_status,
                request=request,
                user=effective_user,
                reason=(
                    reason
                    or "تحديث حالة طلب الصيانة"
                ),
            )
        )

        if changed and normalized_status == MaintenanceRequest.Status.APPROVED:
            door_shift = DoorShift.objects.select_for_update().get(
                pk=updated_maintenance.door_shift_id
            )
            change_door_state(
                door_shift=door_shift,
                new_state=DoorShift.DoorState.MAINTENANCE,
                request=request,
                user=effective_user,
                reason=(
                    "اعتماد وتحويل طلب الصيانة "
                    f"{updated_maintenance.request_number}"
                ),
            )
            from apps.notifications.models import Notification
            from apps.scheduling.models import ShiftOperationalLeadership
            from apps.scheduling.operational_leadership_service import resolve_shift_leader

            maintenance_leader = resolve_shift_leader(
                door_shift.shift_plan,
                ShiftOperationalLeadership.Responsibility.MAINTENANCE_SUPERVISOR,
            )
            if maintenance_leader:
                Notification.objects.create(
                    user=maintenance_leader,
                    title="طلب صيانة معتمد للوردية",
                    message=(
                        f"تم اعتماد الطلب {updated_maintenance.request_number} "
                        "وأصبح جاهزًا للجدولة والتنفيذ."
                    ),
                    section=updated_maintenance.section,
                    url="/ops/maintenance/",
                )

        if (
            changed
            and normalized_status in final_statuses
        ):
            door_shift = (
                DoorShift.objects
                .select_for_update()
                .get(
                    pk=(
                        updated_maintenance
                        .door_shift_id
                    )
                )
            )

            if (
                door_shift.is_active
                and door_shift.shift_plan.is_active
                and (
                    door_shift.state
                    == (
                        DoorShift
                        .DoorState
                        .MAINTENANCE
                    )
                )
            ):
                change_door_state(
                    door_shift=door_shift,
                    new_state=(
                        DoorShift
                        .DoorState
                        .OPEN
                    ),
                    request=request,
                    user=effective_user,
                    reason=(
                        "إعادة فتح الباب بعد "
                        "إنهاء طلب الصيانة "
                        f"{updated_maintenance.request_number}"
                    ),
                )

        updated_maintenance.refresh_from_db()

        if changed and updated_maintenance.source_incident_id:
            from apps.ops.models import IncidentRoutingEvent

            event_map = {
                MaintenanceRequest.Status.APPROVED: IncidentRoutingEvent.EventType.MAINTENANCE_APPROVED,
                MaintenanceRequest.Status.IN_PROGRESS: IncidentRoutingEvent.EventType.MAINTENANCE_STARTED,
                MaintenanceRequest.Status.DONE: IncidentRoutingEvent.EventType.MAINTENANCE_COMPLETED,
                MaintenanceRequest.Status.CLOSED: IncidentRoutingEvent.EventType.MAINTENANCE_COMPLETED,
            }
            event_type = event_map.get(normalized_status)
            if event_type:
                IncidentRoutingEvent.objects.create(
                    incident_id=updated_maintenance.source_incident_id,
                    event_type=event_type,
                    actor=effective_user,
                    note=updated_maintenance.request_number,
                )
                if (
                    event_type == IncidentRoutingEvent.EventType.MAINTENANCE_COMPLETED
                    and updated_maintenance.source_incident.assigned_to_id
                ):
                    from apps.notifications.models import Notification

                    Notification.objects.create(
                        user_id=updated_maintenance.source_incident.assigned_to_id,
                        title="اكتملت صيانة بلاغ تشغيلي",
                        message=(
                            "اكتملت الصيانة المرتبطة بالبلاغ "
                            f"{updated_maintenance.source_incident.incident_number}؛ "
                            "بانتظار تأكيد الإغلاق."
                        ),
                        section=updated_maintenance.source_incident.section,
                        url="/scheduling/",
                        level=Notification.Level.SUCCESS,
                    )

        return updated_maintenance

    @staticmethod
    def change_status(
        *,
        maintenance_request,
        new_status: str,
        request=None,
        user=None,
        reason: str = "",
    ):
        """
        واجهة متوافقة مع الاختبارات
        والخدمات الداخلية.

        Returns:
            tuple:
                updated_request, changed
        """

        return change_maintenance_status(
            maintenance_request=(
                maintenance_request
            ),
            new_status=new_status,
            request=request,
            user=user,
            reason=reason,
        )

    @staticmethod
    def change_maintenance_status(
        *,
        maintenance_request,
        new_status: str,
        request=None,
        user=None,
        reason: str = "",
    ):
        """
        اسم بديل للدالة المركزية.

        Returns:
            tuple:
                updated_request, changed
        """

        return change_maintenance_status(
            maintenance_request=(
                maintenance_request
            ),
            new_status=new_status,
            request=request,
            user=user,
            reason=reason,
        )
