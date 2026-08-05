from __future__ import annotations

from datetime import time
from types import SimpleNamespace

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.audit.models import (
    AssignmentHistory,
    DoorStateHistory,
    IncidentStatusHistory,
    MaintenanceStatusHistory,
    ReportApprovalHistory,
    ShiftPlanHistory,
)
from apps.audit.services import (
    record_assignment_history,
    record_door_state_history,
    record_incident_status_history,
    record_maintenance_status_history,
    record_report_approval_history,
    record_shift_plan_history,
)
from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.ops.models import (
    DoorShift,
    Incident,
    MaintenanceRequest,
)
from apps.reporting.models import ShiftReport


class AuditServicesTests(TestCase):
    """
    اختبارات خدمات إنشاء سجلات المراجعة.
    """

    def setUp(self):
        self.factory = RequestFactory()

        self.user = create_user(
            username="audit_service_user",
            is_staff=True,
        )

        self.request = self.factory.post(
            "/audit/test/",
            REMOTE_ADDR="127.0.0.1",
        )
        self.request.user = self.user

        self.shift_type = create_shift_type(
            name="وردية خدمات التدقيق",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift_plan = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        self.door = create_door(
            door_number=32,
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف خدمات التدقيق",
            employee_number="AUD-S-1001",
            is_active=True,
            can_work_on_doors=True,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift_plan,
            door_number=32,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_record_door_state_history(self):
        """
        خدمة حالة الباب تحفظ القيم والمستخدم والسبب.
        """

        history = record_door_state_history(
            door_shift=self.door_shift,
            old_value={
                "state": DoorShift.DoorState.OPEN,
            },
            new_value={
                "state": DoorShift.DoorState.CLOSED,
            },
            request=self.request,
            reason="إغلاق اختباري",
        )

        self.assertIsInstance(
            history,
            DoorStateHistory,
        )

        self.assertEqual(
            history.changed_by_id,
            self.user.pk,
        )

        self.assertEqual(
            history.change_reason,
            "إغلاق اختباري",
        )

        self.assertEqual(
            history.ip_address,
            "127.0.0.1",
        )

    def test_explicit_user_overrides_request_user(self):
        """
        المستخدم المرسل صراحة له أولوية على مستخدم الطلب.
        """

        explicit_user = create_user(
            username="explicit_audit_user",
        )

        history = record_door_state_history(
            door_shift=self.door_shift,
            old_value={},
            new_value={
                "state": DoorShift.DoorState.CLOSED,
            },
            request=self.request,
            user=explicit_user,
        )

        self.assertEqual(
            history.changed_by_id,
            explicit_user.pk,
        )

    def test_explicit_ip_overrides_request_ip(self):
        """
        عنوان IP المرسل صراحة له أولوية.
        """

        history = record_shift_plan_history(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.UPDATED,
            request=self.request,
            ip_address="10.0.0.10",
        )

        self.assertEqual(
            history.ip_address,
            "10.0.0.10",
        )

    def test_none_snapshots_are_converted_to_empty_dicts(self):
        """
        القيم None تتحول إلى قواميس فارغة.
        """

        history = record_shift_plan_history(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.CREATED,
            old_value=None,
            new_value=None,
            request=self.request,
        )

        self.assertEqual(
            history.old_value,
            {},
        )

        self.assertEqual(
            history.new_value,
            {},
        )

    def test_record_assignment_history(self):
        """
        خدمة سجل التوزيع تحفظ العلاقات الأساسية.
        """

        assignment = DoorAssignment.objects.create(
            shift_plan=self.shift_plan,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            assigned_by=self.user,
            is_active=True,
        )

        history = record_assignment_history(
            assignment=assignment,
            employee=self.employee,
            door=self.door,
            shift_plan=self.shift_plan,
            old_value={},
            new_value={
                "assignment_id": assignment.pk,
            },
            request=self.request,
            reason="إنشاء توزيع",
        )

        self.assertIsInstance(
            history,
            AssignmentHistory,
        )

        self.assertEqual(
            history.assignment_id,
            assignment.pk,
        )

        self.assertEqual(
            history.employee_id,
            self.employee.pk,
        )

        self.assertEqual(
            history.door_id,
            self.door.pk,
        )

        self.assertEqual(
            history.shift_plan_id,
            self.shift_plan.pk,
        )

    def test_record_maintenance_status_history(self):
        """
        خدمة الصيانة تنشئ سجل انتقال الحالة.
        """

        maintenance = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="صيانة لاختبار خدمة التدقيق",
            status=MaintenanceRequest.Status.NEW,
        )

        history = record_maintenance_status_history(
            maintenance_request=maintenance,
            old_value={
                "status": MaintenanceRequest.Status.NEW,
            },
            new_value={
                "status": MaintenanceRequest.Status.APPROVED,
            },
            request=self.request,
            reason="اعتماد الطلب",
        )

        self.assertIsInstance(
            history,
            MaintenanceStatusHistory,
        )

        self.assertEqual(
            history.maintenance_request_id,
            maintenance.pk,
        )

    def test_record_incident_status_history(self):
        """
        خدمة البلاغات تنشئ سجل انتقال الحالة.
        """

        incident = Incident.objects.create(
            shift_plan=self.shift_plan,
            description="بلاغ لاختبار خدمة التدقيق",
            status=Incident.Status.NEW,
        )

        history = record_incident_status_history(
            incident=incident,
            old_value={
                "status": Incident.Status.NEW,
            },
            new_value={
                "status": Incident.Status.IN_PROGRESS,
            },
            request=self.request,
            reason="بدء المعالجة",
        )

        self.assertIsInstance(
            history,
            IncidentStatusHistory,
        )

        self.assertEqual(
            history.incident_id,
            incident.pk,
        )

    def test_record_shift_plan_history(self):
        """
        خدمة الورديات تحفظ نوع الإجراء.
        """

        history = record_shift_plan_history(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.ACTIVATED,
            old_value={
                "is_active": False,
            },
            new_value={
                "is_active": True,
            },
            request=self.request,
            reason="تفعيل الوردية",
        )

        self.assertIsInstance(
            history,
            ShiftPlanHistory,
        )

        self.assertEqual(
            history.action,
            ShiftPlanHistory.Action.ACTIVATED,
        )

    def test_record_report_approval_history(self):
        """
        خدمة اعتماد التقارير تحفظ إجراء الاعتماد.
        """

        self.shift_plan.is_active = False
        self.shift_plan.is_finished = True
        self.shift_plan.save(
            update_fields=[
                "is_active",
                "is_finished",
            ]
        )

        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=self.shift_plan,
            total_doors=41,
            open_doors=41,
        )

        history = record_report_approval_history(
            report=report,
            action=ReportApprovalHistory.Action.SUBMITTED,
            old_value={
                "status": ShiftReport.ReportStatus.DRAFT,
            },
            new_value={
                "status": ShiftReport.ReportStatus.FINAL,
            },
            request=self.request,
            reason="رفع التقرير للاعتماد",
        )

        self.assertIsInstance(
            history,
            ReportApprovalHistory,
        )

        self.assertEqual(
            history.report_id,
            report.pk,
        )

        self.assertEqual(
            history.action,
            ReportApprovalHistory.Action.SUBMITTED,
        )

    def test_service_works_without_request(self):
        """
        يمكن إنشاء سجل نظامي دون طلب HTTP.
        """

        history = record_shift_plan_history(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.UPDATED,
            user=self.user,
            ip_address="127.0.0.2",
            reason="عملية نظامية",
        )

        self.assertEqual(
            history.changed_by_id,
            self.user.pk,
        )

        self.assertEqual(
            history.ip_address,
            "127.0.0.2",
        )