from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
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
    create_user,
)
from apps.distribution.models import DoorAssignment
from apps.ops.models import (
    DoorShift,
    Incident,
    MaintenanceRequest,
)
from apps.reporting.models import ShiftReport


User = get_user_model()


class AuditModelTests(TestCase):
    """
    اختبارات نماذج سجل المراجعة المركزي.
    """

    def setUp(self):
        self.user = create_user(
            username="audit_model_user",
            is_staff=True,
        )

        self.shift_type = create_shift_type(
            name="وردية اختبار التدقيق",
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
            door_number=31,
            is_active=True,
        )

        self.employee = create_employee(
            full_name="موظف سجل التدقيق",
            employee_number="AUD-1001",
            is_active=True,
            can_work_on_doors=True,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift_plan,
            door_number=31,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_door_state_history_can_be_created(self):
        """
        يجب إنشاء سجل تغيير حالة باب.
        """

        history = DoorStateHistory.objects.create(
            door_shift=self.door_shift,
            old_value={
                "state": DoorShift.DoorState.OPEN,
            },
            new_value={
                "state": DoorShift.DoorState.CLOSED,
            },
            changed_by=self.user,
            change_reason="إغلاق تشغيلي",
            ip_address="127.0.0.1",
        )

        self.assertIsNotNone(
            history.pk
        )

        self.assertEqual(
            history.old_value["state"],
            DoorShift.DoorState.OPEN,
        )

        self.assertEqual(
            history.new_value["state"],
            DoorShift.DoorState.CLOSED,
        )

    def test_door_state_history_string_contains_door_number(self):
        """
        النص الظاهر يحتوي رقم الباب.
        """

        history = DoorStateHistory.objects.create(
            door_shift=self.door_shift,
        )

        self.assertIn(
            "31",
            str(history),
        )

    def test_assignment_history_can_be_created(self):
        """
        يجب إنشاء سجل توزيع مركزي.
        """

        assignment = DoorAssignment.objects.create(
            shift_plan=self.shift_plan,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.user,
        )

        history = AssignmentHistory.objects.create(
            assignment=assignment,
            employee=self.employee,
            door=self.door,
            shift_plan=self.shift_plan,
            old_value={},
            new_value={
                "employee_id": self.employee.pk,
                "door_id": self.door.pk,
            },
            changed_by=self.user,
            change_reason="إنشاء توزيع",
        )

        self.assertIsNotNone(
            history.pk
        )

        self.assertEqual(
            history.employee_id,
            self.employee.pk,
        )

        self.assertEqual(
            history.door_id,
            self.door.pk,
        )

    def test_assignment_history_survives_assignment_deletion(self):
        """
        حذف التوزيع لا يحذف سجل التدقيق.
        """

        assignment = DoorAssignment.objects.create(
            shift_plan=self.shift_plan,
            door=self.door,
            employee=self.employee,
            role=DoorAssignment.Role.MONITOR,
            is_active=True,
            assigned_by=self.user,
        )

        history = AssignmentHistory.objects.create(
            assignment=assignment,
            employee=self.employee,
            door=self.door,
            shift_plan=self.shift_plan,
            new_value={
                "assignment_id": assignment.pk,
            },
            changed_by=self.user,
        )

        history_pk = history.pk

        assignment.delete()

        history.refresh_from_db()

        self.assertEqual(
            history.pk,
            history_pk,
        )

        self.assertIsNone(
            history.assignment_id
        )

        self.assertEqual(
            history.employee_id,
            self.employee.pk,
        )

    def test_shift_plan_history_action_label(self):
        """
        يجب عرض اسم إجراء الوردية بالعربية.
        """

        history = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.ACTIVATED,
            old_value={
                "is_active": False,
            },
            new_value={
                "is_active": True,
            },
            changed_by=self.user,
        )

        self.assertEqual(
            history.get_action_display(),
            "تفعيل",
        )

        self.assertIn(
            "تفعيل",
            str(history),
        )

    def test_base_history_defaults_to_empty_json(self):
        """
        القيم السابقة والجديدة تكون قاموسًا فارغًا افتراضيًا.
        """

        history = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.CREATED,
        )

        self.assertEqual(
            history.old_value,
            {},
        )

        self.assertEqual(
            history.new_value,
            {},
        )

    def test_history_records_user_reason_and_ip(self):
        """
        يجب حفظ المستخدم والسبب وعنوان IP.
        """

        history = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.UPDATED,
            changed_by=self.user,
            change_reason="تعديل وقت الوردية",
            ip_address="192.168.1.10",
        )

        self.assertEqual(
            history.changed_by_id,
            self.user.pk,
        )

        self.assertEqual(
            history.change_reason,
            "تعديل وقت الوردية",
        )

        self.assertEqual(
            history.ip_address,
            "192.168.1.10",
        )

    def test_history_ordering_is_newest_first(self):
        """
        الترتيب الافتراضي يجب أن يكون من الأحدث إلى الأقدم.
        """

        first = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.CREATED,
        )

        second = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.UPDATED,
        )

        history_ids = list(
            ShiftPlanHistory.objects.values_list(
                "id",
                flat=True,
            )
        )

        self.assertEqual(
            history_ids,
            [
                second.pk,
                first.pk,
            ],
        )

    def test_changed_by_becomes_null_after_user_deletion(self):
        """
        حذف المستخدم لا يحذف سجل التدقيق.
        """

        history = ShiftPlanHistory.objects.create(
            shift_plan=self.shift_plan,
            action=ShiftPlanHistory.Action.UPDATED,
            changed_by=self.user,
        )

        history_pk = history.pk

        self.user.delete()

        history.refresh_from_db()

        self.assertEqual(
            history.pk,
            history_pk,
        )

        self.assertIsNone(
            history.changed_by_id
        )

    def test_report_approval_history_action_label(self):
        """
        يجب دعم إجراءات اعتماد التقارير.
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

        history = ReportApprovalHistory.objects.create(
            report=report,
            action=ReportApprovalHistory.Action.SUBMITTED,
            changed_by=self.user,
            new_value={
                "status": ShiftReport.ReportStatus.FINAL,
            },
        )

        self.assertEqual(
            history.get_action_display(),
            "رفع للاعتماد",
        )

        self.assertIn(
            "رفع للاعتماد",
            str(history),
        )

    def test_maintenance_history_can_be_created(self):
        """
        يجب إنشاء سجل تغيير حالة صيانة.
        """

        maintenance = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="اختبار سجل الصيانة",
            status=MaintenanceRequest.Status.NEW,
        )

        history = MaintenanceStatusHistory.objects.create(
            maintenance_request=maintenance,
            old_value={
                "status": MaintenanceRequest.Status.NEW,
            },
            new_value={
                "status": MaintenanceRequest.Status.APPROVED,
            },
            changed_by=self.user,
        )

        self.assertIsNotNone(
            history.pk
        )

        self.assertEqual(
            history.maintenance_request_id,
            maintenance.pk,
        )

    def test_incident_history_can_be_created(self):
        """
        يجب إنشاء سجل تغيير حالة بلاغ.
        """

        incident = Incident.objects.create(
            shift_plan=self.shift_plan,
            description="بلاغ لاختبار سجل التدقيق",
            status=Incident.Status.NEW,
        )

        history = IncidentStatusHistory.objects.create(
            incident=incident,
            old_value={
                "status": Incident.Status.NEW,
            },
            new_value={
                "status": Incident.Status.IN_PROGRESS,
            },
            changed_by=self.user,
        )

        self.assertIsNotNone(
            history.pk
        )

        self.assertEqual(
            history.incident_id,
            incident.pk,
        )