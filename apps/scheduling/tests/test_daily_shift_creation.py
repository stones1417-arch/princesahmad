from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from apps.scheduling.models import ShiftPlan, ShiftType
from apps.scheduling.views import (
    ensure_default_shift_types,
    ensure_today_shift_plans,
)


class DailyShiftCreationTests(TestCase):
    """
    اختبارات إنشاء الورديات اليومية الرسمية.
    """

    def test_default_shift_types_are_created(self):
        """
        يجب إنشاء أنواع الورديات الرسمية الأربع.
        """

        ensure_default_shift_types()

        names = set(
            ShiftType.objects.values_list(
                "name",
                flat=True,
            )
        )

        self.assertTrue(
            {
                "الفجر",
                "الضحى",
                "المسائية",
                "المشتركة",
            }.issubset(names)
        )

    def test_today_shift_plans_are_created(self):
        """
        يجب إنشاء أربع خطط ورديات لليوم الحالي.
        """

        ensure_today_shift_plans()

        today = timezone.localdate()

        shifts = ShiftPlan.objects.filter(
            date=today,
            category=ShiftPlan.ShiftCategory.DAILY,
            shift_type__name__in=[
                "الفجر",
                "الضحى",
                "المسائية",
                "المشتركة",
            ],
        )

        self.assertEqual(
            shifts.count(),
            4,
        )

    def test_today_shift_creation_is_idempotent(self):
        """
        إعادة التنفيذ لا تنشئ ورديات يومية مكررة.
        """

        ensure_today_shift_plans()
        ensure_today_shift_plans()

        today = timezone.localdate()

        shifts_count = (
            ShiftPlan.objects
            .filter(
                date=today,
                category=(
                    ShiftPlan
                    .ShiftCategory
                    .DAILY
                ),
                shift_type__name__in=[
                    "الفجر",
                    "الضحى",
                    "المسائية",
                    "المشتركة",
                ],
            )
            .count()
        )

        self.assertEqual(
            shifts_count,
            4,
        )

    def test_daily_shift_uses_shift_type_effective_times(self):
        """
        الخطط اليومية تستخدم أوقات نوع الوردية عند غياب الأوقات الخاصة.
        """

        ensure_today_shift_plans()

        shift = (
            ShiftPlan.objects
            .select_related("shift_type")
            .get(
                date=timezone.localdate(),
                shift_type__name="الفجر",
                category=(
                    ShiftPlan
                    .ShiftCategory
                    .DAILY
                ),
            )
        )

        self.assertIsNone(
            shift.start_time
        )

        self.assertIsNone(
            shift.end_time
        )

        self.assertEqual(
            shift.effective_start_time,
            shift.shift_type.start_time,
        )

        self.assertEqual(
            shift.effective_end_time,
            shift.shift_type.end_time,
        )