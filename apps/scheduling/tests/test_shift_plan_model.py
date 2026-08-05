from __future__ import annotations

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.scheduling.models import ShiftPlan


class ShiftPlanModelTests(TestCase):
    """
    اختبارات قواعد نموذج خطة الوردية.
    """

    def test_daily_shift_is_created_successfully(self):
        """
        يجب إنشاء وردية يومية صحيحة.
        """

        shift_type = create_shift_type(
            name="وردية يومية",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            category=ShiftPlan.ShiftCategory.DAILY,
        )

        self.assertIsNotNone(
            shift.pk
        )

        self.assertEqual(
            shift.category,
            ShiftPlan.ShiftCategory.DAILY,
        )

        self.assertFalse(
            shift.is_active
        )

        self.assertFalse(
            shift.is_finished
        )

    def test_active_and_finished_cannot_be_true_together(self):
        """
        لا يمكن أن تكون الوردية نشطة ومنتهية معًا.
        """

        shift_type = create_shift_type(
            name="وردية تعارض الحالة",
        )

        shift = ShiftPlan(
            shift_type=shift_type,
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            category=ShiftPlan.ShiftCategory.DAILY,
            is_active=True,
            is_finished=True,
        )

        with self.assertRaises(
            ValidationError
        ):
            shift.full_clean()

    def test_equal_start_and_end_times_are_rejected(self):
        """
        وقت البداية والنهاية لا يمكن أن يكونا متساويين.
        """

        shift_type = create_shift_type(
            name="وردية وقت متساوٍ",
        )

        shift = ShiftPlan(
            shift_type=shift_type,
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(8, 0),
            category=ShiftPlan.ShiftCategory.DAILY,
        )

        with self.assertRaises(
            ValidationError
        ):
            shift.full_clean()

    def test_end_before_start_requires_crosses_midnight(self):
        """
        الوردية التي تنتهي بعد منتصف الليل يجب تمييزها بذلك.
        """

        shift_type = create_shift_type(
            name="وردية ليلية",
        )

        shift = ShiftPlan(
            shift_type=shift_type,
            date=timezone.localdate(),
            start_time=time(21, 0),
            end_time=time(2, 0),
            crosses_midnight=False,
            category=ShiftPlan.ShiftCategory.DAILY,
        )

        with self.assertRaises(
            ValidationError
        ):
            shift.full_clean()

    def test_cross_midnight_shift_duration_is_correct(self):
        """
        حساب مدة الوردية الممتدة لليوم التالي.
        """

        shift_type = create_shift_type(
            name="وردية مشتركة",
            start_time=time(21, 0),
            end_time=time(2, 0),
        )

        shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(21, 0),
            end_time=time(2, 0),
            crosses_midnight=True,
        )

        self.assertEqual(
            shift.duration_minutes,
            300,
        )

    def test_overlapping_shifts_are_rejected(self):
        """
        يجب منع إنشاء ورديتين متداخلتين زمنيًا.
        """

        today = timezone.localdate()

        first_type = create_shift_type(
            name="الوردية الأولى",
        )

        second_type = create_shift_type(
            name="الوردية الثانية",
        )

        create_shift_plan(
            shift_type=first_type,
            shift_date=today,
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        overlapping_shift = ShiftPlan(
            shift_type=second_type,
            date=today,
            start_time=time(15, 0),
            end_time=time(20, 0),
            category=ShiftPlan.ShiftCategory.DAILY,
        )

        with self.assertRaises(
            ValidationError
        ):
            overlapping_shift.full_clean()

    def test_adjacent_shifts_are_allowed(self):
        """
        يسمح بورديتين متتاليتين دون تداخل.
        """

        today = timezone.localdate()

        first_type = create_shift_type(
            name="وردية صباحية",
        )

        second_type = create_shift_type(
            name="وردية مسائية",
        )

        create_shift_plan(
            shift_type=first_type,
            shift_date=today,
            start_time=time(8, 0),
            end_time=time(14, 0),
        )

        second_shift = create_shift_plan(
            shift_type=second_type,
            shift_date=today,
            start_time=time(14, 0),
            end_time=time(20, 0),
        )

        self.assertIsNotNone(
            second_shift.pk
        )

    def test_previous_day_cross_midnight_overlap_is_rejected(self):
        """
        يجب اكتشاف التداخل مع وردية اليوم السابق
        إذا امتدت لما بعد منتصف الليل.
        """

        today = timezone.localdate()

        night_type = create_shift_type(
            name="وردية ليلية سابقة",
        )

        morning_type = create_shift_type(
            name="وردية فجر جديدة",
        )

        create_shift_plan(
            shift_type=night_type,
            shift_date=today - timedelta(days=1),
            start_time=time(21, 0),
            end_time=time(3, 0),
            crosses_midnight=True,
        )

        morning_shift = ShiftPlan(
            shift_type=morning_type,
            date=today,
            start_time=time(2, 0),
            end_time=time(8, 0),
            category=ShiftPlan.ShiftCategory.DAILY,
        )

        with self.assertRaises(
            ValidationError
        ):
            morning_shift.full_clean()

    def test_effective_times_fall_back_to_shift_type(self):
        """
        الورديات اليومية بلا أوقات مخصصة تستخدم أوقات النوع.
        """

        shift_type = create_shift_type(
            name="وردية افتراضية",
            start_time=time(7, 30),
            end_time=time(14, 30),
        )

        shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=None,
            end_time=None,
        )

        self.assertEqual(
            shift.effective_start_time,
            time(7, 30),
        )

        self.assertEqual(
            shift.effective_end_time,
            time(14, 30),
        )