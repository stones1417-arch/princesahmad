from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.ops.models import Incident, MaintenanceRequest
from apps.scheduling.models import ShiftPlan
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.reporting.models import ShiftReport
from apps.scheduling.models import ShiftPlan
from django.core.exceptions import ValidationError


@transaction.atomic
def finish_shift(
    *,
    shift_plan: ShiftPlan,
    finished_by,
) -> ShiftPlan:
    shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(pk=shift_plan.pk)
    )

    open_incidents = Incident.objects.filter(
        shift_plan=shift,
    ).exclude(
        status__in=[
            Incident.Status.CLOSED,
            Incident.Status.RESOLVED,
        ]
    )

    open_maintenance = MaintenanceRequest.objects.filter(
        door_shift__shift_plan=shift,
    ).exclude(
        status__in=[
            MaintenanceRequest.Status.CLOSED,
            MaintenanceRequest.Status.COMPLETED,
        ]
    )

    if open_incidents.exists():
        raise ValidationError(
            "لا يمكن إنهاء الوردية قبل معالجة البلاغات المفتوحة."
        )

    if open_maintenance.exists():
        raise ValidationError(
            "لا يمكن إنهاء الوردية قبل معالجة طلبات الصيانة المفتوحة."
        )

    shift.is_active = False
    shift.is_finished = True
    shift.finished_by = finished_by
    shift.finished_at = timezone.now()

    shift.save(
        update_fields=[
            "is_active",
            "is_finished",
            "finished_by",
            "finished_at",
        ]
    )
@transaction.atomic
def create_final_shift_report(
    *,
    shift_plan: ShiftPlan,
    created_by,
    **report_data,
) -> ShiftReport:
    shift = (
        ShiftPlan.objects
        .select_for_update()
        .get(pk=shift_plan.pk)
    )

    if shift.is_active:
        raise ValidationError(
            "لا يمكن إنشاء تقرير نهائي لوردية ما زالت نشطة."
        )

    if not shift.is_finished:
        raise ValidationError(
            "يجب إنهاء الوردية قبل إنشاء التقرير النهائي."
        )

    return ShiftReport.objects.create(
        shift_plan=shift,
        created_by=created_by,
        status=ShiftReport.ReportStatus.FINAL,
        **report_data,
    )
from django.core.exceptions import ValidationError


def delete(self, *args, **kwargs):
    if self.shift_assignments.exists():
        raise ValidationError(
            "لا يمكن حذف وردية لها تسكين موظفين."
        )

    if self.door_assignments.exists():
        raise ValidationError(
            "لا يمكن حذف وردية لها توزيعات أبواب."
        )

    if hasattr(self, "report"):
        raise ValidationError(
            "لا يمكن حذف وردية لها تقرير."
        )

    return super().delete(*args, **kwargs)

    return shift
shift_plan = models.ForeignKey(
    ShiftPlan,
    on_delete=models.PROTECT,
)
shift_plan = models.OneToOneField(
    ShiftPlan,
    on_delete=models.PROTECT,
)