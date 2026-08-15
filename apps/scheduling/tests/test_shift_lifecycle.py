from __future__ import annotations

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_door,
    create_shift_plan,
    create_shift_type,
)
from apps.ops.models import DoorShift
from apps.scheduling.services import (
    activate_shift,
    deactivate_shift,
    ensure_shift_door_states,
    finish_shift,
)


class ShiftLifecycleTests(TestCase):
    """
    اختبارات دورة حياة الوردية.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية دورة الحياة",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=False,
            is_finished=False,
        )

    def test_shift_can_be_activated(self):
        """
        يجب تفعيل الوردية الصحيحة.
        """

        activated_shift = activate_shift(
            self.shift
        )

        self.assertTrue(
            activated_shift.is_active
        )

        self.assertFalse(
            activated_shift.is_finished
        )

        self.assertIsNotNone(
            activated_shift.activated_at
        )

    def test_finished_shift_cannot_be_activated(self):
        """
        لا يمكن تفعيل وردية منتهية.
        """

        self.shift.is_active = False
        self.shift.is_finished = True
        self.shift.finished_at = timezone.now()
        self.shift.save()

        with self.assertRaises(
            ValidationError
        ):
            activate_shift(
                self.shift
            )

    def test_activating_new_shift_finishes_previous_active_shift(self):
        """
        تفعيل وردية جديدة يجب أن ينهي الوردية النشطة السابقة.
        """

        first_shift = activate_shift(
            self.shift
        )

        second_type = create_shift_type(
            name="وردية تالية",
            start_time=time(16, 0),
            end_time=time(20, 0),
        )

        second_shift = create_shift_plan(
            shift_type=second_type,
            shift_date=timezone.localdate(),
            start_time=time(16, 0),
            end_time=time(20, 0),
        )

        activated_second = activate_shift(
            second_shift
        )

        first_shift.refresh_from_db()

        self.assertFalse(
            first_shift.is_active
        )

        self.assertTrue(
            first_shift.is_finished
        )

        self.assertIsNotNone(
            first_shift.finished_at
        )

        self.assertTrue(
            activated_second.is_active
        )

        self.assertFalse(
            activated_second.is_finished
        )

    def test_only_one_active_shift_remains(self):
        """
        بعد التفعيل يجب ألا توجد إلا وردية نشطة واحدة.
        """

        activate_shift(
            self.shift
        )

        second_type = create_shift_type(
            name="وردية نشطة ثانية",
        )

        second_shift = create_shift_plan(
            shift_type=second_type,
            shift_date=(
                timezone.localdate()
                + timedelta(days=1)
            ),
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        activate_shift(
            second_shift
        )

        active_count = (
            type(self.shift).objects
            .filter(is_active=True)
            .count()
        )

        self.assertEqual(
            active_count,
            1,
        )

    def test_active_shift_can_be_finished(self):
        """
        يجب إنهاء الوردية النشطة.
        """

        activate_shift(
            self.shift
        )

        finished_shift = finish_shift(
            self.shift
        )

        self.assertFalse(
            finished_shift.is_active
        )

        self.assertTrue(
            finished_shift.is_finished
        )

        self.assertIsNotNone(
            finished_shift.finished_at
        )

    def test_finish_shift_is_idempotent(self):
        """
        تكرار إنهاء الوردية لا يسبب خطأ.
        """

        activate_shift(
            self.shift
        )

        finish_shift(
            self.shift
        )

        second_result = finish_shift(
            self.shift
        )

        self.assertTrue(
            second_result.is_finished
        )

        self.assertFalse(
            second_result.is_active
        )

    def test_deactivate_shift_does_not_finish_it(self):
        """
        إلغاء التفعيل لا يعني إنهاء الوردية.
        """

        activate_shift(
            self.shift
        )

        deactivated_shift = deactivate_shift(
            self.shift
        )

        self.assertFalse(
            deactivated_shift.is_active
        )

        self.assertFalse(
            deactivated_shift.is_finished
        )

    def test_invalid_shift_object_is_rejected(self):
        """
        الخدمات يجب أن ترفض أي كائن ليس ShiftPlan.
        """

        with self.assertRaises(
            ValidationError
        ):
            activate_shift(
                object()
            )

        with self.assertRaises(
            ValidationError
        ):
            finish_shift(
                object()
            )

        with self.assertRaises(
            ValidationError
        ):
            deactivate_shift(
                object()
            )


class ShiftDoorStatesTests(TestCase):
    """
    اختبارات إنشاء حالات الأبواب للوردية.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية حالات الأبواب",
        )

        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        self.first_door = create_door(
            door_number=1,
        )

        self.second_door = create_door(
            door_number=2,
        )

        self.inactive_door = create_door(
            door_number=3,
            is_active=False,
        )

    def test_ensure_shift_door_states_creates_active_doors_only(self):
        """
        يجب إنشاء حالة لكل باب نشط فقط.
        """

        created_count = ensure_shift_door_states(
            self.shift
        )

        self.assertEqual(
            created_count,
            2,
        )

        door_numbers = set(
            DoorShift.objects
            .filter(shift_plan=self.shift)
            .values_list(
                "door_number",
                flat=True,
            )
        )

        self.assertEqual(
            door_numbers,
            {
                "1",
                "2",
            },
        )

    def test_ensure_shift_door_states_does_not_duplicate_records(self):
        """
        إعادة تنفيذ الخدمة لا تنشئ سجلات مكررة.
        """

        ensure_shift_door_states(
            self.shift
        )

        second_created_count = (
            ensure_shift_door_states(
                self.shift
            )
        )

        self.assertEqual(
            second_created_count,
            0,
        )

        self.assertEqual(
            DoorShift.objects
            .filter(shift_plan=self.shift)
            .count(),
            2,
        )

    def test_ensure_shift_door_states_keeps_textual_official_codes(self):
        """
        يجب الاحتفاظ برقم الباب النصي الرسمي مثل 6A و 6B عند إنشاء حالات الأبواب.
        """

        for door_code in (
            "5",
            "6B",
            "6A",
            "7",
            "8",
            "9",
        ):
            create_door(
                door_number=door_code,
            )

        created_count = ensure_shift_door_states(
            self.shift,
        )

        self.assertEqual(
            created_count,
            8,
        )

        ordered_door_numbers = list(
            DoorShift.objects
            .filter(shift_plan=self.shift)
            .order_by("sort_order", "door_number")
            .values_list("door_number", flat=True)
        )

        self.assertEqual(
            ordered_door_numbers,
            [
                "1",
                "2",
                "5",
                "6B",
                "6A",
                "7",
                "8",
                "9",
            ],
        )

    def test_activation_creates_door_states(self):
        """
        تفعيل الوردية ينشئ حالات الأبواب تلقائيًا.
        """

        activate_shift(
            self.shift
        )

        self.assertEqual(
            DoorShift.objects
            .filter(
                shift_plan=self.shift,
                is_active=True,
            )
            .count(),
            2,
        )

    def test_finishing_shift_deactivates_door_states(self):
        """
        إنهاء الوردية يعطل جميع حالات أبوابها.
        """

        activate_shift(
            self.shift
        )

        finish_shift(
            self.shift
        )

        self.assertFalse(
            DoorShift.objects
            .filter(
                shift_plan=self.shift,
                is_active=True,
            )
            .exists()
        )

    def test_deactivating_shift_deactivates_door_states(self):
        """
        إلغاء تفعيل الوردية يعطل حالات الأبواب.
        """

        activate_shift(
            self.shift
        )

        deactivate_shift(
            self.shift
        )

        self.assertFalse(
            DoorShift.objects
            .filter(
                shift_plan=self.shift,
                is_active=True,
            )
            .exists()
        )