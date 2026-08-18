from django.core.exceptions import ValidationError
from django.conf import settings

from apps.core.notification_service import NotificationService
from apps.core.services import BaseService
from apps.dashboard.models import SystemActivityLog
from apps.distribution.models import DoorAssignment
from apps.locations.models import Door
from apps.ops.models import DoorShift, MaintenanceRequest
from apps.scheduling.models import ShiftAssignment

from .ai_summary import (
    build_executive_summary,
    build_recommendations,
)
from .models import ShiftReport


class ReportService(BaseService):
    """
    خدمات التقارير التشغيلية والإدارية
    """

    module_name = "التقارير"

    @staticmethod
    def render_pdf(html: str) -> bytes:
        """Render report HTML with the deployment-safe PDF engine."""
        from weasyprint import HTML

        return HTML(
            string=html,
            base_url=str(settings.BASE_DIR),
        ).write_pdf()

    @staticmethod
    def report_section_for_shift(shift_plan):
        sections = set(
            DoorAssignment.objects.filter(
                shift_plan=shift_plan,
                is_active=True,
            ).values_list("section", flat=True)
        )
        if not sections:
            sections = set(
                DoorShift.objects.filter(
                    shift_plan=shift_plan,
                ).exclude(section="").values_list("section", flat=True)
            )
        if sections == {"male"}:
            return ShiftReport.OperationalSection.MALE
        if sections == {"female"}:
            return ShiftReport.OperationalSection.FEMALE
        return ShiftReport.OperationalSection.ALL

    @classmethod
    def generate_shift_report(cls, *, request=None, shift_plan, user):
        """
        توليد تقرير وردية احترافي كامل
        """

        if not shift_plan.is_finished:
            raise ValidationError("لا يمكن إنشاء تقرير لوردية غير منتهية")

        if ShiftReport.objects.filter(shift_plan=shift_plan).exists():
            raise ValidationError("تم إنشاء تقرير لهذه الوردية مسبقًا")

        door_shifts = DoorShift.objects.filter(
            shift_plan=shift_plan
        )
        door_map = {
            door.door_number: door
            for door in Door.objects.filter(
                door_number__in=door_shifts.values_list(
                    "door_number",
                    flat=True,
                )
            )
        }

        assignments = ShiftAssignment.objects.filter(
            shift_plan=shift_plan
        )
        door_assignments = (
            DoorAssignment.objects.filter(
                shift_plan=shift_plan,
            ).select_related(
                "door",
                "employee",
            )
        )

        maintenance_requests = MaintenanceRequest.objects.filter(
            door_shift__shift_plan=shift_plan
        )

        total_doors = door_shifts.count()
        open_doors = door_shifts.filter(state=DoorShift.DoorState.OPEN).count()
        closed_doors = door_shifts.filter(state=DoorShift.DoorState.CLOSED).count()
        maintenance_doors = door_shifts.filter(state=DoorShift.DoorState.MAINTENANCE).count()
        total_employees = assignments.count()
        total_maintenance_requests = maintenance_requests.count()

        completed_maintenance_requests = maintenance_requests.filter(
            status=MaintenanceRequest.Status.DONE
        ).count()

        snapshot_data = {
            "shift": {
                "id": shift_plan.id,
                "date": str(shift_plan.date),
                "type": shift_plan.shift_type.name,
                "status": (
                    "منتهية"
                    if shift_plan.is_finished
                    else "نشطة"
                    if shift_plan.is_active
                    else "غير نشطة"
                ),
            },
            "doors": [
                {
                    "door_number": d.door_number,
                    "operational_section": getattr(
                        door_map.get(d.door_number),
                        "operational_section",
                        "",
                    ),
                    "state": d.get_state_display(),
                    "supervisor": str(d.supervisor) if d.supervisor else None,
                    "notes": d.notes,
                }
                for d in door_shifts
            ],
            "maintenance_requests": [
                {
                    "door_number": m.door_shift.door_number,
                    "description": m.description,
                    "status": m.get_status_display(),
                    "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for m in maintenance_requests
            ],
            "employees": [
                {
                    "employee": a.employee.full_name,
                    "confirmed": a.is_confirmed,
                }
                for a in assignments
            ],
            "door_assignments": [
                {
                    "door_number": a.door.door_number,
                    "employee": a.employee.full_name,
                    "section": a.section,
                    "role": a.role,
                    "is_active": a.is_active,
                }
                for a in door_assignments
            ],
        }

        with cls.atomic():
            report = ShiftReport.objects.create(
                report_type=ShiftReport.ReportType.OPERATIONAL,
                operational_section=cls.report_section_for_shift(shift_plan),
                shift_plan=shift_plan,
                total_doors=total_doors,
                open_doors=open_doors,
                closed_doors=closed_doors,
                maintenance_doors=maintenance_doors,
                total_employees=total_employees,
                total_maintenance_requests=total_maintenance_requests,
                completed_maintenance_requests=completed_maintenance_requests,
                snapshot_data=snapshot_data,
                created_by=user,
                status=ShiftReport.ReportStatus.DRAFT,
            )

            report.summary = build_executive_summary(report)
            report.recommendations = "\n".join(
                build_recommendations(report)
            )

            report.save(
                update_fields=[
                    "summary",
                    "recommendations",
                ]
            )
            report.finalize()

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.CREATE,
                description=f"تم إنشاء تقرير تشغيلي رقم {report.report_number}",
            )

            NotificationService.success(
                title="تم إنشاء تقرير وردية",
                message=f"تم إنشاء تقرير تشغيلي رقم {report.report_number}",
                user=request.user if request else user,
                url=f"/reporting/{report.pk}/",
            )

        return report

    @classmethod
    def approve_report(cls, *, request, report, user):
        """
        اعتماد التقرير
        """

        with cls.atomic():
            report.approve(user)

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.APPROVE,
                description=f"تم اعتماد التقرير رقم {report.report_number}",
            )

            NotificationService.success(
                title="تم اعتماد تقرير",
                message=f"تم اعتماد التقرير رقم {report.report_number}",
                user=request.user,
                url=f"/reporting/{report.pk}/",
            )

        return report

    @classmethod
    def regenerate_summary(cls, *, request, report):
        """
        إعادة توليد الملخص والتوصيات
        """

        with cls.atomic():
            report.summary = build_executive_summary(report)
            report.recommendations = "\n".join(
                build_recommendations(report)
            )

            report.save(
                update_fields=[
                    "summary",
                    "recommendations",
                ]
            )

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم تحديث ملخص وتوصيات التقرير رقم {report.report_number}",
            )

            NotificationService.info(
                title="تم تحديث تقرير",
                message=f"تم تحديث ملخص وتوصيات التقرير رقم {report.report_number}",
                user=request.user,
                url=f"/reporting/{report.pk}/",
            )

        return report


def generate_shift_report(shift_plan, user, request=None):
    """
    دالة توافقية حتى لا تتعطل الاستدعاءات القديمة
    """

    return ReportService.generate_shift_report(
        request=request,
        shift_plan=shift_plan,
        user=user,
    )
