from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.factories import (
    create_shift_plan,
    create_shift_type,
)
from apps.ops.incident_service import (
    change_incident_status,
)
from apps.ops.models import (
    DoorShift,
    Incident,
)


User = get_user_model()


class IncidentModelTests(TestCase):
    """
    اختبارات نموذج البلاغ التشغيلي.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية اختبار البلاغات",
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
            door_number=7,
            state=DoorShift.DoorState.OPEN,
            is_active=True,
        )

    def test_incident_number_is_generated(self):
        """
        يجب توليد رقم بلاغ تلقائيًا.
        """

        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ تجريبي",
        )

        self.assertTrue(
            incident.incident_number.startswith("INC-")
        )

    def test_door_shift_sets_shift_plan_automatically(self):
        """
        عند تحديد الباب، يجب ربط البلاغ بالوردية تلقائيًا.
        """

        incident = Incident.objects.create(
            door_shift=self.door_shift,
            description="بلاغ على باب",
        )

        self.assertEqual(
            incident.shift_plan_id,
            self.shift.id,
        )

    def test_empty_description_is_rejected(self):
        """
        يجب رفض البلاغ دون وصف.
        """

        incident = Incident(
            shift_plan=self.shift,
            description="   ",
        )

        with self.assertRaises(ValidationError):
            incident.full_clean()

    def test_closed_incident_requires_notes(self):
        """
        يجب منع إغلاق البلاغ دون ملاحظات.
        """

        incident = Incident(
            shift_plan=self.shift,
            description="بلاغ يحتاج إغلاق",
            status=Incident.Status.CLOSED,
            closing_notes="",
        )

        with self.assertRaises(ValidationError):
            incident.full_clean()

    def test_closed_at_is_set_for_closed_status(self):
        """
        يجب تسجيل وقت إغلاق البلاغ.
        """

        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ مغلق",
            status=Incident.Status.CLOSED,
            closing_notes="تم الحل",
        )

        self.assertIsNotNone(
            incident.closed_at
        )

    def test_reopening_incident_clears_closed_at(self):
        """
        إعادة فتح البلاغ تمسح وقت الإغلاق.
        """

        incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ يعاد فتحه",
            status=Incident.Status.CLOSED,
            closing_notes="تم الإغلاق",
        )

        incident.status = Incident.Status.IN_PROGRESS
        incident.save()

        self.assertIsNone(
            incident.closed_at
        )


class IncidentStatusServiceTests(TestCase):
    """
    اختبارات خدمة انتقال حالة البلاغ.
    """

    def setUp(self):
        shift_type = create_shift_type(
            name="وردية خدمة البلاغات",
        )

        self.shift = create_shift_plan(
            shift_type=shift_type,
            shift_date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_active=True,
        )

        self.user = User.objects.create_user(
            username="incident_operator",
            password="StrongPassword123!",
            is_active=True,
        )

        self.incident = Incident.objects.create(
            shift_plan=self.shift,
            description="بلاغ خدمة",
            status=Incident.Status.NEW,
        )

    @patch(
        "apps.audit.services.record_incident_status_history"
    )
    def test_incident_status_can_be_changed(
        self,
        history_mock,
    ):
        """
        يجب تغيير حالة البلاغ وتسجيلها.
        """

        updated_incident, changed = (
            change_incident_status(
                incident=self.incident,
                new_status=Incident.Status.IN_PROGRESS,
                reason="بدء معالجة البلاغ",
                user=self.user,
            )
        )

        self.assertTrue(changed)

        self.assertEqual(
            updated_incident.status,
            Incident.Status.IN_PROGRESS,
        )

        history_mock.assert_called_once()

    @patch(
        "apps.audit.services.record_incident_status_history"
    )
    def test_closing_sets_time_user_and_notes(
        self,
        history_mock,
    ):
        """
        إغلاق البلاغ يسجل الوقت والمستخدم والملاحظات.
        """

        updated_incident, changed = (
            change_incident_status(
                incident=self.incident,
                new_status=Incident.Status.CLOSED,
                reason="إغلاق البلاغ",
                closing_notes="تمت معالجة البلاغ",
                user=self.user,
            )
        )

        self.assertTrue(changed)

        self.assertEqual(
            updated_incident.status,
            Incident.Status.CLOSED,
        )

        self.assertIsNotNone(
            updated_incident.closed_at
        )

        self.assertEqual(
            updated_incident.closed_by_id,
            self.user.id,
        )

        self.assertEqual(
            updated_incident.closing_notes,
            "تمت معالجة البلاغ",
        )

    @patch(
        "apps.audit.services.record_incident_status_history"
    )
    def test_same_status_does_not_create_history(
        self,
        history_mock,
    ):
        """
        الحالة نفسها لا تنشئ سجلًا جديدًا.
        """

        updated_incident, changed = (
            change_incident_status(
                incident=self.incident,
                new_status=Incident.Status.NEW,
            )
        )

        self.assertFalse(changed)

        self.assertEqual(
            updated_incident.status,
            Incident.Status.NEW,
        )

        history_mock.assert_not_called()

    def test_invalid_incident_status_is_rejected(self):
        """
        يجب رفض حالة بلاغ غير صحيحة.
        """

        with self.assertRaises(ValidationError):
            change_incident_status(
                incident=self.incident,
                new_status="invalid_status",
            )

    def test_none_incident_is_rejected(self):
        """
        يجب رفض بلاغ غير موجود.
        """

        with self.assertRaises(ValidationError):
            change_incident_status(
                incident=None,
                new_status=Incident.Status.CLOSED,
            )

    @patch(
        "apps.audit.services.record_incident_status_history"
    )
    def test_reopening_clears_close_fields(
        self,
        history_mock,
    ):
        """
        إعادة فتح البلاغ تمسح وقت ومنفذ الإغلاق.
        """

        closed_incident, _changed = (
            change_incident_status(
                incident=self.incident,
                new_status=Incident.Status.CLOSED,
                closing_notes="تم الإغلاق",
                user=self.user,
            )
        )

        reopened_incident, changed = (
            change_incident_status(
                incident=closed_incident,
                new_status=Incident.Status.IN_PROGRESS,
                reason="إعادة فتح البلاغ",
                user=self.user,
            )
        )

        self.assertTrue(changed)

        self.assertIsNone(
            reopened_incident.closed_at
        )

        self.assertIsNone(
            reopened_incident.closed_by_id
        )