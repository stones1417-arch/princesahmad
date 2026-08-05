from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import (
    AssignmentHistory,
    DoorStateHistory,
    IncidentStatusHistory,
    MaintenanceStatusHistory,
    ReportApprovalHistory,
    ShiftPlanHistory,
)
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
)
from apps.distribution.models import DoorAssignment
from apps.ops.door_service import change_door_state
from apps.ops.incident_service import change_incident_status
from apps.ops.maintenance_service import change_maintenance_status
from apps.ops.models import (
    DoorShift,
    Incident,
    MaintenanceRequest,
)
from apps.reporting.models import ShiftReport
from apps.scheduling.services import (
    activate_shift,
    finish_shift,
)


User = get_user_model()


class FullShiftLifecycleE2ETests(TestCase):
    """
    اختبار دورة تشغيل كاملة للوردية.
    """

    def setUp(self):
        self.operator = User.objects.create_user(
            username="e2e_operator",
            password="StrongPassword123!",
            is_staff=True,
            is_active=True,
        )

        self.approver = User.objects.create_user(
            username="e2e_approver",
            password="StrongPassword123!",
            is_staff=True,
            is_active=True,
        )

        permission = Permission.objects.get(
            codename="can_approve_shift_report",
            content_type__app_label="reporting",
        )

        self.approver.user_permissions.add(permission)

        self.shift_type = create_shift_type(
            name="وردية تكامل شاملة",
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=False,
        )

        self.door = create_door(
            door_number=1,
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف تكامل شامل",
            employee_number="E2E-1001",
            is_active=True,
            can_work_on_doors=True,
        )

    def test_complete_shift_operational_cycle(self):
        """
        دورة كاملة:
        تفعيل وردية
        ثم توزيع موظف
        ثم تغيير حالة باب
        ثم صيانة
        ثم بلاغ
        ثم إنهاء الوردية
        ثم إنشاء تقرير
        ثم اعتماد التقرير.
        """

        # 1. تفعيل الوردية
        activated_shift = activate_shift(self.shift)

        self.assertTrue(
            activated_shift.is_active
        )

        self.assertFalse(
            activated_shift.is_finished
        )

        # 2. التأكد من إنشاء حالات الأبواب
        door_shift = DoorShift.objects.get(
            shift_plan=activated_shift,
            door_number=self.door.door_number,
        )

        self.assertTrue(
            door_shift.is_active
        )

        # 3. توزيع موظف على الباب
        assignment = DoorAssignment.objects.create(
            shift_plan=activated_shift,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            assigned_by=self.operator,
            is_active=True,
        )

        self.assertIsNotNone(
            assignment.pk
        )

        # 4. تغيير حالة الباب
        updated_door_shift, changed = change_door_state(
            door_shift=door_shift,
            new_state=DoorShift.DoorState.CLOSED,
            user=self.operator,
            reason="إغلاق الباب مؤقتًا للاختبار",
        )

        self.assertTrue(changed)

        self.assertEqual(
            updated_door_shift.state,
            DoorShift.DoorState.CLOSED,
        )

        self.assertTrue(
            DoorStateHistory.objects.filter(
                door_shift=door_shift,
            ).exists()
        )

        # 5. إنشاء طلب صيانة
        maintenance = MaintenanceRequest.objects.create(
            door_shift=door_shift,
            description="طلب صيانة ضمن اختبار شامل",
            status=MaintenanceRequest.Status.NEW,
        )

        self.assertIsNotNone(
            maintenance.pk
        )

        # 6. تغيير حالة الصيانة
        maintenance, changed = change_maintenance_status(
            maintenance_request=maintenance,
            new_status=MaintenanceRequest.Status.IN_PROGRESS,
            user=self.operator,
            reason="بدء أعمال الصيانة",
        )

        self.assertTrue(changed)

        self.assertTrue(
            MaintenanceStatusHistory.objects.filter(
                maintenance_request=maintenance,
            ).exists()
        )

        # 7. إنشاء بلاغ
        incident = Incident.objects.create(
            shift_plan=activated_shift,
            door_shift=door_shift,
            description="بلاغ تشغيلي ضمن اختبار شامل",
            status=Incident.Status.NEW,
        )

        self.assertIsNotNone(
            incident.pk
        )

        # 8. معالجة البلاغ
        incident, changed = change_incident_status(
            incident=incident,
            new_status=Incident.Status.IN_PROGRESS,
            user=self.operator,
            reason="بدء معالجة البلاغ",
        )

        self.assertTrue(changed)

        self.assertTrue(
            IncidentStatusHistory.objects.filter(
                incident=incident,
            ).exists()
        )

        # 9. إغلاق البلاغ
        incident, changed = change_incident_status(
            incident=incident,
            new_status=Incident.Status.CLOSED,
            user=self.operator,
            reason="إغلاق البلاغ بعد المعالجة",
            closing_notes="تمت المعالجة بنجاح.",
        )

        self.assertTrue(changed)

        # 10. إنهاء الصيانة
        maintenance, changed = change_maintenance_status(
            maintenance_request=maintenance,
            new_status=MaintenanceRequest.Status.CLOSED,
            user=self.operator,
            reason="إغلاق طلب الصيانة",
        )

        self.assertTrue(changed)

        # 11. إنهاء الوردية
        finished_shift = finish_shift(
            activated_shift
        )

        self.assertTrue(
            finished_shift.is_finished
        )

        self.assertFalse(
            finished_shift.is_active
        )

        # 12. إنشاء التقرير
        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=finished_shift,
            status=ShiftReport.ReportStatus.DRAFT,
            total_doors=1,
            open_doors=0,
            closed_doors=1,
            maintenance_doors=0,
            total_employees=1,
            total_maintenance_requests=1,
            completed_maintenance_requests=1,
            summary="تقرير نهاية وردية الاختبار الشامل",
            created_by=self.operator,
        )

        self.assertIsNotNone(
            report.pk
        )

        self.assertTrue(
            report.report_number.startswith("SR-")
        )

        # 13. تحويل التقرير إلى نهائي
        report.finalize()
        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ShiftReport.ReportStatus.FINAL,
        )

        # 14. اعتماد التقرير
        report.approve(
            self.approver
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ShiftReport.ReportStatus.APPROVED,
        )

        self.assertEqual(
            report.approved_by_id,
            self.approver.pk,
        )