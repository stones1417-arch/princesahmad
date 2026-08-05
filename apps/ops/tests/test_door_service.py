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
from apps.ops.door_service import change_door_state
from apps.ops.models import DoorShift


class DoorStateServiceTests(TestCase):
    """
    اختبارات خدمة تغيير حالة الباب.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية اختبار حالة الباب",
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
            door_number=1,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    @patch(
        "apps.audit.services.record_door_state_history"
    )
    def test_change_door_state_updates_state(
        self,
        history_mock,
    ):
        """
        يجب تغيير حالة الباب إلى الحالة المطلوبة.
        """

        updated_door, changed = change_door_state(
            door_shift=self.door_shift,
            new_state=DoorShift.DoorState.CLOSED,
            reason="إغلاق تشغيلي",
        )

        self.assertTrue(changed)

        self.assertEqual(
            updated_door.state,
            DoorShift.DoorState.CLOSED,
        )

        self.door_shift.refresh_from_db()

        self.assertEqual(
            self.door_shift.state,
            DoorShift.DoorState.CLOSED,
        )

        history_mock.assert_called_once()

    @patch(
        "apps.audit.services.record_door_state_history"
    )
    def test_same_state_does_not_create_history(
        self,
        history_mock,
    ):
        """
        عدم تغير الحالة لا ينشئ سجلًا تاريخيًا جديدًا.
        """

        updated_door, changed = change_door_state(
            door_shift=self.door_shift,
            new_state=DoorShift.DoorState.OPEN,
        )

        self.assertFalse(changed)

        self.assertEqual(
            updated_door.state,
            DoorShift.DoorState.OPEN,
        )

        history_mock.assert_not_called()

    def test_invalid_door_state_is_rejected(self):
        """
        يجب رفض حالة غير موجودة ضمن الخيارات الرسمية.
        """

        with self.assertRaises(ValidationError):
            change_door_state(
                door_shift=self.door_shift,
                new_state="invalid_state",
            )

    def test_none_door_shift_is_rejected(self):
        """
        يجب رفض سجل باب غير موجود.
        """

        with self.assertRaises(ValidationError):
            change_door_state(
                door_shift=None,
                new_state=DoorShift.DoorState.CLOSED,
            )

    def test_unsaved_door_shift_is_rejected(self):
        """
        يجب رفض سجل باب غير محفوظ.
        """

        unsaved_door = DoorShift(
            shift_plan=self.shift,
            door_number=2,
            state=DoorShift.DoorState.OPEN,
        )

        with self.assertRaises(ValidationError):
            change_door_state(
                door_shift=unsaved_door,
                new_state=DoorShift.DoorState.CLOSED,
            )

    @patch(
        "apps.audit.services.record_door_state_history"
    )
    def test_default_reason_is_used_when_reason_empty(
        self,
        history_mock,
    ):
        """
        يجب تسجيل سبب افتراضي عند عدم إرسال سبب.
        """

        change_door_state(
            door_shift=self.door_shift,
            new_state=DoorShift.DoorState.SECURED,
            reason="   ",
        )

        call_kwargs = history_mock.call_args.kwargs

        self.assertEqual(
            call_kwargs["reason"],
            "تحديث حالة الباب من لوحة العمليات",
        )

    @patch(
        "apps.audit.services.record_door_state_history"
    )
    def test_history_contains_old_and_new_state(
        self,
        history_mock,
    ):
        """
        السجل التاريخي يجب أن يحتوي الحالة السابقة والجديدة.
        """

        change_door_state(
            door_shift=self.door_shift,
            new_state=DoorShift.DoorState.MAINTENANCE,
            reason="بدء الصيانة",
        )

        call_kwargs = history_mock.call_args.kwargs

        self.assertEqual(
            call_kwargs["old_value"]["state"],
            DoorShift.DoorState.OPEN,
        )

        self.assertEqual(
            call_kwargs["new_value"]["state"],
            DoorShift.DoorState.MAINTENANCE,
        )