from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.ops.maintenance_service import (
    change_maintenance_status,
)
from apps.ops.models import (
    DoorShift,
    MaintenanceRequest,
)


class MaintenanceRequestModelTests(TestCase):
    """
    اختبارات نموذج طلب الصيانة.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية اختبار الصيانة",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=5,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def create_request(
        self,
        **overrides,
    ) -> MaintenanceRequest:
        data = {
            "door_shift": self.door_shift,
            "description": "عطل تجريبي في الباب",
            "priority": MaintenanceRequest.Priority.HIGH,
            "status": MaintenanceRequest.Status.NEW,
        }

        data.update(overrides)

        request_obj = MaintenanceRequest(
            **data
        )

        request_obj.full_clean()
        request_obj.save()

        return request_obj

    def test_request_number_is_generated(self):
        """
        يجب توليد رقم طلب صيانة تلقائيًا.
        """

        maintenance = self.create_request()

        self.assertTrue(
            maintenance.request_number.startswith("MR-")
        )

    def test_request_numbers_are_unique(self):
        """
        يجب توليد أرقام متسلسلة غير مكررة.
        """

        first = self.create_request()
        second = self.create_request(
            description="عطل ثانٍ",
        )

        self.assertNotEqual(
            first.request_number,
            second.request_number,
        )

    def test_inactive_door_shift_is_rejected(self):
        """
        لا يسمح بطلب صيانة لباب غير نشط.
        """

        self.door_shift.is_active = False
        self.door_shift.save(
            update_fields=["is_active"]
        )

        maintenance = MaintenanceRequest(
            door_shift=self.door_shift,
            description="اختبار باب غير نشط",
        )

        with self.assertRaises(ValidationError):
            maintenance.full_clean()

    def test_inactive_shift_is_rejected(self):
        """
        لا يسمح بطلب صيانة لوردية غير نشطة.
        """

        self.shift.is_active = False
        self.shift.save(
            update_fields=["is_active"]
        )

        maintenance = MaintenanceRequest(
            door_shift=self.door_shift,
            description="اختبار وردية غير نشطة",
        )

        with self.assertRaises(ValidationError):
            maintenance.full_clean()

    def test_assigned_status_requires_technician(self):
        """
        التحويل للفريق الفني يتطلب تحديد فني.
        """

        maintenance = MaintenanceRequest(
            door_shift=self.door_shift,
            description="طلب دون فني",
            status=MaintenanceRequest.Status.ASSIGNED,
        )

        with self.assertRaises(ValidationError):
            maintenance.full_clean()

    def test_closed_status_requires_closing_notes(self):
        """
        يجب منع إغلاق الصيانة دون ملاحظات.
        """

        maintenance = MaintenanceRequest(
            door_shift=self.door_shift,
            description="طلب إغلاق دون ملاحظات",
            status=MaintenanceRequest.Status.CLOSED,
            closing_notes="",
        )

        with self.assertRaises(ValidationError):
            maintenance.full_clean()

    def test_rating_must_be_between_zero_and_five(self):
        """
        تقييم الصيانة يجب أن يكون بين صفر وخمسة.
        """

        maintenance = MaintenanceRequest(
            door_shift=self.door_shift,
            description="اختبار التقييم",
            rating=6,
        )

        with self.assertRaises(ValidationError):
            maintenance.full_clean()

    def test_status_change_records_transition_times(self):
        """
        يجب تسجيل أوقات انتقال حالات الصيانة.
        """

        maintenance = self.create_request()

        maintenance.status = (
            MaintenanceRequest.Status.APPROVED
        )
        maintenance.save()

        self.assertIsNotNone(
            maintenance.approved_at
        )

        maintenance.technician_name = "الفني التجريبي"
        maintenance.status = (
            MaintenanceRequest.Status.ASSIGNED
        )
        maintenance.save()

        self.assertIsNotNone(
            maintenance.assigned_at
        )

        maintenance.status = (
            MaintenanceRequest.Status.IN_PROGRESS
        )
        maintenance.save()

        self.assertIsNotNone(
            maintenance.started_at
        )

        maintenance.status = (
            MaintenanceRequest.Status.FIXED
        )
        maintenance.save()

        self.assertIsNotNone(
            maintenance.fixed_at
        )

        maintenance.closing_notes = "تم الإصلاح والإغلاق"
        maintenance.status = (
            MaintenanceRequest.Status.CLOSED
        )
        maintenance.save()

        self.assertIsNotNone(
            maintenance.closed_at
        )


class MaintenanceStatusServiceTests(TestCase):
    """
    اختبارات خدمة انتقال حالة طلب الصيانة.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية خدمة الصيانة",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=6,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

        self.maintenance = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="اختبار خدمة الصيانة",
            status=MaintenanceRequest.Status.NEW,
        )

    @patch(
        "apps.audit.services.record_maintenance_status_history"
    )
    def test_status_can_be_changed(
        self,
        history_mock,
    ):
        """
        يجب تغيير حالة طلب الصيانة.
        """

        updated_request, changed = (
            change_maintenance_status(
                maintenance_request=self.maintenance,
                new_status=(
                    MaintenanceRequest.Status.APPROVED
                ),
                reason="اعتماد الطلب",
            )
        )

        self.assertTrue(changed)

        self.assertEqual(
            updated_request.status,
            MaintenanceRequest.Status.APPROVED,
        )

        self.assertIsNotNone(
            updated_request.approved_at
        )

        history_mock.assert_called_once()

    @patch(
        "apps.audit.services.record_maintenance_status_history"
    )
    def test_same_status_does_not_create_history(
        self,
        history_mock,
    ):
        """
        الحالة نفسها لا تنشئ سجلًا تاريخيًا.
        """

        updated_request, changed = (
            change_maintenance_status(
                maintenance_request=self.maintenance,
                new_status=MaintenanceRequest.Status.NEW,
            )
        )

        self.assertFalse(changed)

        self.assertEqual(
            updated_request.status,
            MaintenanceRequest.Status.NEW,
        )

        history_mock.assert_not_called()

    def test_invalid_status_is_rejected(self):
        """
        يجب رفض حالة صيانة غير صحيحة.
        """

        with self.assertRaises(ValidationError):
            change_maintenance_status(
                maintenance_request=self.maintenance,
                new_status="invalid_status",
            )

    def test_none_request_is_rejected(self):
        """
        يجب رفض طلب غير موجود.
        """

        with self.assertRaises(ValidationError):
            change_maintenance_status(
                maintenance_request=None,
                new_status=MaintenanceRequest.Status.APPROVED,
            )

    def test_unsaved_request_is_rejected(self):
        """
        يجب رفض طلب صيانة غير محفوظ.
        """

        unsaved_request = MaintenanceRequest(
            door_shift=self.door_shift,
            description="طلب غير محفوظ",
        )

        with self.assertRaises(ValidationError):
            change_maintenance_status(
                maintenance_request=unsaved_request,
                new_status=MaintenanceRequest.Status.APPROVED,
            )

    @patch(
        "apps.audit.services.record_maintenance_status_history"
    )
    def test_history_contains_old_and_new_status(
        self,
        history_mock,
    ):
        """
        السجل التاريخي يحتوي الحالة السابقة والجديدة.
        """

        change_maintenance_status(
            maintenance_request=self.maintenance,
            new_status=MaintenanceRequest.Status.APPROVED,
            reason="اعتماد",
        )

        call_kwargs = history_mock.call_args.kwargs

        self.assertEqual(
            call_kwargs["old_value"]["status"],
            MaintenanceRequest.Status.NEW,
        )

        self.assertEqual(
            call_kwargs["new_value"]["status"],
            MaintenanceRequest.Status.APPROVED,
        )