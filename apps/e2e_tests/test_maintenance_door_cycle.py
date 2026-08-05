from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import (
    DoorStateHistory,
    MaintenanceStatusHistory,
)
from apps.core.tests.factories import (
    create_door,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.ops.door_service import (
    change_door_state,
)
from apps.ops.maintenance_service import (
    change_maintenance_status,
)
from apps.ops.models import (
    DoorShift,
    MaintenanceRequest,
)
from apps.scheduling.services import (
    activate_shift,
    finish_shift,
)


class MaintenanceDoorCycleE2ETests(TestCase):
    """
    اختبارات End-to-End لدورة صيانة الباب.

    تغطي:
    - تفعيل الوردية.
    - إنشاء حالة الباب.
    - فتح طلب صيانة.
    - تحويل الباب إلى الصيانة.
    - تسجيل سجل تدقيق لحالة الباب.
    - بدء أعمال الصيانة.
    - منع إغلاق الصيانة دون ملاحظات.
    - إصلاح العطل.
    - إغلاق طلب الصيانة.
    - إعادة الباب إلى الحالة المفتوحة.
    - إنهاء الوردية.
    """

    def setUp(self):
        self.operator = create_user(
            username="e2e_maintenance_operator",
            is_staff=True,
            is_active=True,
        )

        self.shift_type = create_shift_type(
            name="وردية اختبار صيانة الباب",
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
            door_number=4,
            is_active=True,
        )

    def _activate_shift_and_get_door_state(
        self,
    ) -> tuple:
        """
        تفعيل الوردية وإرجاع الوردية وحالة الباب.
        """

        active_shift = activate_shift(
            self.shift
        )

        door_shift = DoorShift.objects.get(
            shift_plan=active_shift,
            door_number=self.door.door_number,
        )

        return (
            active_shift,
            door_shift,
        )

    def _create_maintenance_request(
        self,
        door_shift: DoorShift,
    ) -> MaintenanceRequest:
        """
        إنشاء طلب صيانة جديد.
        """

        return MaintenanceRequest.objects.create(
            door_shift=door_shift,
            description=(
                "عطل تشغيلي في الباب ضمن "
                "اختبار End-to-End"
            ),
            status=(
                MaintenanceRequest
                .Status
                .NEW
            ),
        )

    def test_complete_maintenance_door_cycle(self):
        """
        دورة صيانة كاملة للباب من فتح الطلب
        حتى إعادة الباب إلى الحالة المفتوحة.
        """

        # ==================================================
        # 1. تفعيل الوردية
        # ==================================================

        active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        self.assertTrue(
            active_shift.is_active
        )

        self.assertFalse(
            active_shift.is_finished
        )

        self.assertTrue(
            door_shift.is_active
        )

        self.assertEqual(
            door_shift.state,
            DoorShift.DoorState.OPEN,
        )

        # ==================================================
        # 2. إنشاء طلب الصيانة
        # ==================================================

        maintenance_request = (
            self._create_maintenance_request(
                door_shift
            )
        )

        self.assertIsNotNone(
            maintenance_request.pk
        )

        self.assertEqual(
            maintenance_request.status,
            MaintenanceRequest.Status.NEW,
        )

        self.assertTrue(
            maintenance_request.request_number
        )

        # ==================================================
        # 3. تحويل حالة الباب إلى صيانة
        # ==================================================

        door_shift, door_changed = (
            change_door_state(
                door_shift=door_shift,
                new_state=(
                    DoorShift
                    .DoorState
                    .MAINTENANCE
                ),
                user=self.operator,
                reason=(
                    "تحويل الباب إلى الصيانة "
                    "بعد فتح طلب صيانة"
                ),
            )
        )

        self.assertTrue(
            door_changed
        )

        self.assertEqual(
            door_shift.state,
            DoorShift.DoorState.MAINTENANCE,
        )

        door_maintenance_history = (
            DoorStateHistory.objects.filter(
                door_shift=door_shift,
                new_value__state=(
                    DoorShift
                    .DoorState
                    .MAINTENANCE
                ),
            )
        )

        self.assertTrue(
            door_maintenance_history.exists()
        )

        # ==================================================
        # 4. بدء أعمال الصيانة
        # ==================================================

        maintenance_request, changed = (
            change_maintenance_status(
                maintenance_request=(
                    maintenance_request
                ),
                new_status=(
                    MaintenanceRequest
                    .Status
                    .IN_PROGRESS
                ),
                user=self.operator,
                reason="بدء أعمال الصيانة على الباب",
            )
        )

        self.assertTrue(
            changed
        )

        maintenance_request.refresh_from_db()

        self.assertEqual(
            maintenance_request.status,
            (
                MaintenanceRequest
                .Status
                .IN_PROGRESS
            ),
        )

        if hasattr(
            maintenance_request,
            "started_at",
        ):
            self.assertIsNotNone(
                maintenance_request.started_at
            )

        self.assertTrue(
            MaintenanceStatusHistory.objects.filter(
                maintenance_request=(
                    maintenance_request
                ),
                old_value__status=(
                    MaintenanceRequest
                    .Status
                    .NEW
                ),
                new_value__status=(
                    MaintenanceRequest
                    .Status
                    .IN_PROGRESS
                ),
            ).exists()
        )

        # ==================================================
        # 5. تسجيل إصلاح العطل
        # ==================================================

        maintenance_request, changed = (
            change_maintenance_status(
                maintenance_request=(
                    maintenance_request
                ),
                new_status=(
                    MaintenanceRequest
                    .Status
                    .FIXED
                ),
                user=self.operator,
                reason="تم إصلاح العطل بنجاح",
            )
        )

        self.assertTrue(
            changed
        )

        maintenance_request.refresh_from_db()

        self.assertEqual(
            maintenance_request.status,
            MaintenanceRequest.Status.FIXED,
        )

        if hasattr(
            maintenance_request,
            "fixed_at",
        ):
            self.assertIsNotNone(
                maintenance_request.fixed_at
            )

        self.assertTrue(
            MaintenanceStatusHistory.objects.filter(
                maintenance_request=(
                    maintenance_request
                ),
                new_value__status=(
                    MaintenanceRequest
                    .Status
                    .FIXED
                ),
            ).exists()
        )

        # ==================================================
        # 6. إضافة ملاحظات الإغلاق
        # ==================================================

        if hasattr(
            maintenance_request,
            "closing_notes",
        ):
            maintenance_request.closing_notes = (
                "تمت صيانة الباب واختباره "
                "وأصبح جاهزًا للتشغيل."
            )

            maintenance_request.save(
                update_fields=[
                    "closing_notes",
                    "updated_at",
                ]
                if hasattr(
                    maintenance_request,
                    "updated_at",
                )
                else [
                    "closing_notes",
                ]
            )

        # ==================================================
        # 7. إغلاق طلب الصيانة
        # ==================================================

        maintenance_request, changed = (
            change_maintenance_status(
                maintenance_request=(
                    maintenance_request
                ),
                new_status=(
                    MaintenanceRequest
                    .Status
                    .CLOSED
                ),
                user=self.operator,
                reason=(
                    "إغلاق طلب الصيانة "
                    "بعد التحقق من نجاح الإصلاح"
                ),
            )
        )

        self.assertTrue(
            changed
        )

        maintenance_request.refresh_from_db()

        self.assertEqual(
            maintenance_request.status,
            MaintenanceRequest.Status.CLOSED,
        )

        if hasattr(
            maintenance_request,
            "closed_at",
        ):
            self.assertIsNotNone(
                maintenance_request.closed_at
            )

        self.assertTrue(
            MaintenanceStatusHistory.objects.filter(
                maintenance_request=(
                    maintenance_request
                ),
                new_value__status=(
                    MaintenanceRequest
                    .Status
                    .CLOSED
                ),
            ).exists()
        )

        # ==================================================
        # 8. إعادة حالة الباب إلى مفتوح
        # ==================================================

        door_shift, door_changed = (
            change_door_state(
                door_shift=door_shift,
                new_state=(
                    DoorShift
                    .DoorState
                    .OPEN
                ),
                user=self.operator,
                reason=(
                    "إعادة فتح الباب بعد "
                    "إنهاء أعمال الصيانة"
                ),
            )
        )

        self.assertTrue(
            door_changed
        )

        self.assertEqual(
            door_shift.state,
            DoorShift.DoorState.OPEN,
        )

        self.assertTrue(
            DoorStateHistory.objects.filter(
                door_shift=door_shift,
                old_value__state=(
                    DoorShift
                    .DoorState
                    .MAINTENANCE
                ),
                new_value__state=(
                    DoorShift
                    .DoorState
                    .OPEN
                ),
            ).exists()
        )

        # ==================================================
        # 9. التحقق من عدد انتقالات الحالة
        # ==================================================

        maintenance_history_count = (
            MaintenanceStatusHistory.objects
            .filter(
                maintenance_request=(
                    maintenance_request
                )
            )
            .count()
        )

        self.assertEqual(
            maintenance_history_count,
            3,
        )

        door_history_count = (
            DoorStateHistory.objects
            .filter(
                door_shift=door_shift
            )
            .count()
        )

        self.assertEqual(
            door_history_count,
            2,
        )

        # ==================================================
        # 10. إنهاء الوردية
        # ==================================================

        finished_shift = finish_shift(
            active_shift
        )

        finished_shift.refresh_from_db()
        door_shift.refresh_from_db()

        self.assertFalse(
            finished_shift.is_active
        )

        self.assertTrue(
            finished_shift.is_finished
        )

        self.assertFalse(
            door_shift.is_active
        )

    def test_closing_maintenance_without_notes_is_rejected(self):
        """
        يجب منع إغلاق طلب الصيانة دون ملاحظات إغلاق.
        """

        _active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        maintenance_request = (
            self._create_maintenance_request(
                door_shift
            )
        )

        maintenance_request.status = (
            MaintenanceRequest
            .Status
            .CLOSED
        )

        if hasattr(
            maintenance_request,
            "closing_notes",
        ):
            maintenance_request.closing_notes = ""

        with self.assertRaises(
            ValidationError
        ):
            maintenance_request.full_clean()

    def test_same_door_state_does_not_create_duplicate_history(self):
        """
        إرسال حالة الباب نفسها لا ينشئ سجل تدقيق جديدًا.
        """

        _active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        history_count_before = (
            DoorStateHistory.objects
            .filter(
                door_shift=door_shift
            )
            .count()
        )

        door_shift, changed = change_door_state(
            door_shift=door_shift,
            new_state=DoorShift.DoorState.OPEN,
            user=self.operator,
            reason="إرسال الحالة نفسها",
        )

        history_count_after = (
            DoorStateHistory.objects
            .filter(
                door_shift=door_shift
            )
            .count()
        )

        self.assertFalse(
            changed
        )

        self.assertEqual(
            history_count_after,
            history_count_before,
        )

    def test_same_maintenance_status_does_not_create_history(self):
        """
        إرسال حالة الصيانة نفسها لا ينشئ سجلًا تاريخيًا.
        """

        _active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        maintenance_request = (
            self._create_maintenance_request(
                door_shift
            )
        )

        history_count_before = (
            MaintenanceStatusHistory.objects
            .filter(
                maintenance_request=(
                    maintenance_request
                )
            )
            .count()
        )

        maintenance_request, changed = (
            change_maintenance_status(
                maintenance_request=(
                    maintenance_request
                ),
                new_status=(
                    MaintenanceRequest
                    .Status
                    .NEW
                ),
                user=self.operator,
                reason="إرسال الحالة نفسها",
            )
        )

        history_count_after = (
            MaintenanceStatusHistory.objects
            .filter(
                maintenance_request=(
                    maintenance_request
                )
            )
            .count()
        )

        self.assertFalse(
            changed
        )

        self.assertEqual(
            history_count_after,
            history_count_before,
        )

    def test_invalid_door_state_is_rejected(self):
        """
        يجب رفض حالة باب غير معتمدة.
        """

        _active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        with self.assertRaises(
            ValidationError
        ):
            change_door_state(
                door_shift=door_shift,
                new_state="invalid-state",
                user=self.operator,
                reason="اختبار حالة غير صحيحة",
            )

    def test_invalid_maintenance_status_is_rejected(self):
        """
        يجب رفض حالة صيانة غير معتمدة.
        """

        _active_shift, door_shift = (
            self._activate_shift_and_get_door_state()
        )

        maintenance_request = (
            self._create_maintenance_request(
                door_shift
            )
        )

        with self.assertRaises(
            ValidationError
        ):
            change_maintenance_status(
                maintenance_request=(
                    maintenance_request
                ),
                new_status="invalid-status",
                user=self.operator,
                reason="اختبار حالة غير صحيحة",
            )