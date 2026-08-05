from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.ops.models import (
    DoorShift,
    MaintenanceRequest,
)


class MaintenanceRequestTests(TestCase):
    """
    اختبارات طلبات الصيانة.
    """

    def setUp(self):
        self.shift_type = create_shift_type(
            name="وردية الصيانة",
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

        self.door_shift = DoorShift.objects.create(
            shift_plan=self.shift,
            door_number=10,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_maintenance_request_generates_number(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="عطل في حساس الباب",
        )

        self.assertTrue(
            request_obj.request_number.startswith(
                "MR-"
            )
        )

    def test_maintenance_request_numbers_are_sequential(self):
        first = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="العطل الأول",
        )

        second = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="العطل الثاني",
        )

        first_number = int(
            first.request_number.split("-")[-1]
        )

        second_number = int(
            second.request_number.split("-")[-1]
        )

        self.assertEqual(
            second_number,
            first_number + 1,
        )

    def test_request_is_open_by_default(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="عطل تشغيلي",
        )

        self.assertTrue(
            request_obj.is_open_request
        )

        self.assertFalse(
            request_obj.is_final_status
        )

    def test_assigned_status_requires_technician(self):
        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="عطل يحتاج فني",
            status=MaintenanceRequest.Status.ASSIGNED,
        )

        with self.assertRaises(
            ValidationError
        ):
            request_obj.full_clean()

    def test_closed_status_requires_closing_notes(self):
        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="طلب صيانة مكتمل",
            status=MaintenanceRequest.Status.CLOSED,
            closing_notes="",
        )

        with self.assertRaises(
            ValidationError
        ):
            request_obj.full_clean()

    def test_rating_must_be_between_zero_and_five(self):
        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="طلب تقييم",
            rating=6,
        )

        with self.assertRaises(
            ValidationError
        ):
            request_obj.full_clean()

    def test_inactive_door_shift_is_rejected(self):
        self.door_shift.is_active = False
        self.door_shift.save(
            update_fields=[
                "is_active",
            ]
        )

        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="عطل على باب غير نشط",
        )

        with self.assertRaises(
            ValidationError
        ):
            request_obj.full_clean()

    def test_inactive_shift_is_rejected(self):
        self.shift.is_active = False
        self.shift.save(
            update_fields=[
                "is_active",
            ]
        )

        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="عطل في وردية غير نشطة",
        )

        with self.assertRaises(
            ValidationError
        ):
            request_obj.full_clean()

    def test_approved_status_sets_approved_at(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="طلب للاعتماد",
        )

        request_obj.status = (
            MaintenanceRequest.Status.APPROVED
        )

        request_obj.save()
        request_obj.refresh_from_db()

        self.assertIsNotNone(
            request_obj.approved_at
        )

    def test_in_progress_status_sets_started_at(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="طلب قيد التنفيذ",
        )

        request_obj.status = (
            MaintenanceRequest.Status.IN_PROGRESS
        )

        request_obj.save()
        request_obj.refresh_from_db()

        self.assertIsNotNone(
            request_obj.started_at
        )

    def test_fixed_status_sets_fixed_at(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="طلب تم إصلاحه",
        )

        request_obj.status = (
            MaintenanceRequest.Status.FIXED
        )

        request_obj.save()
        request_obj.refresh_from_db()

        self.assertIsNotNone(
            request_obj.fixed_at
        )

    def test_closed_status_sets_closed_at(self):
        request_obj = MaintenanceRequest.objects.create(
            door_shift=self.door_shift,
            description="طلب للإغلاق",
        )

        request_obj.status = (
            MaintenanceRequest.Status.CLOSED
        )

        request_obj.closing_notes = (
            "تم الإصلاح والتأكد من التشغيل"
        )

        request_obj.full_clean()
        request_obj.save()
        request_obj.refresh_from_db()

        self.assertIsNotNone(
            request_obj.closed_at
        )

        self.assertTrue(
            request_obj.is_final_status
        )

    def test_progress_percentage_is_correct(self):
        request_obj = MaintenanceRequest(
            door_shift=self.door_shift,
            description="اختبار المؤشر",
            status=(
                MaintenanceRequest
                .Status
                .IN_PROGRESS
            ),
        )

        self.assertEqual(
            request_obj.progress_percentage,
            70,
        )