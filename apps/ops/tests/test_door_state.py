from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_shift_plan,
    create_shift_type,
)
from apps.ops.models import (
    DoorCurrentState,
    DoorShift,
)


class DoorShiftModelTests(TestCase):
    """
    اختبارات حالة الباب المرتبطة بالوردية.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية حالات الأبواب",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
            is_finished=False,
        )

    def test_door_shift_can_be_created_for_active_shift(self):
        door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=1,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

        self.assertIsNotNone(
            door_shift.pk
        )

        self.assertEqual(
            door_shift.state,
            DoorShift.DoorState.OPEN,
        )

    def test_door_shift_rejects_inactive_shift(self):
        self.shift.is_active = False
        self.shift.save(
            update_fields=[
                "is_active",
            ]
        )

        door_shift = DoorShift(
            shift_plan=self.shift,
            door_number=2,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            door_shift.full_clean()

    def test_duplicate_door_shift_in_same_shift_is_rejected(self):
        DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=3,
            state=DoorShift.DoorState.OPEN,
        )

        duplicate = DoorShift(
            shift_plan=self.shift,
            door_number=3,
            state=DoorShift.DoorState.CLOSED,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate.full_clean()

    def test_different_doors_can_exist_in_same_shift(self):
        first = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=4,
            state=DoorShift.DoorState.OPEN,
        )

        second = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=5,
            state=DoorShift.DoorState.CLOSED,
        )

        self.assertNotEqual(
            first.door_number,
            second.door_number,
        )


class DoorCurrentStateTests(TestCase):
    """
    اختبارات المصدر الرسمي للحالة الحالية للباب.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية الحالة الحالية",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.door = create_door(
            door_number=6,
        )

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=6,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_current_state_can_be_created(self):
        current_state = DoorCurrentState.objects.create(
            door=self.door,
            state=DoorShift.DoorState.OPEN,
            current_shift=self.door_shift,
            update_source=(
                DoorCurrentState
                .UpdateSource
                .OPERATIONS
            ),
        )

        self.assertIsNotNone(
            current_state.pk
        )

        self.assertEqual(
            current_state.state,
            DoorShift.DoorState.OPEN,
        )

    def test_only_one_current_state_per_door(self):
        DoorCurrentState.objects.create(
            door=self.door,
            state=DoorShift.DoorState.OPEN,
        )

        duplicate = DoorCurrentState(
            door=self.door,
            state=DoorShift.DoorState.CLOSED,
        )

        with self.assertRaises(
            ValidationError
        ):
            duplicate.full_clean()

    def test_current_state_can_reference_current_shift(self):
        current_state = DoorCurrentState.objects.create(
            door=self.door,
            state=DoorShift.DoorState.MAINTENANCE,
            current_shift=self.door_shift,
            update_source=(
                DoorCurrentState
                .UpdateSource
                .MAINTENANCE
            ),
        )

        self.assertEqual(
            current_state.current_shift,
            self.door_shift,
        )

        self.assertEqual(
            current_state.update_source,
            DoorCurrentState.UpdateSource.MAINTENANCE,
        )