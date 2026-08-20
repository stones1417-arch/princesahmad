from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.factories import (
    create_employee,
    create_shift_plan,
    create_shift_type,
    create_user,
)
from apps.ops.models import DoorShift
from apps.reporting.models import ShiftReport
from apps.scheduling.models import ShiftAssignment
from apps.scheduling.services import finish_shift as official_finish_shift


class FinishShiftViewTests(TestCase):
    success_message = (
        "تم إنهاء الوردية بنجاح، يرجى مراجعة التقرير واعتماده."
    )

    def setUp(self):
        self.user = create_user(
            username="finish-shift-admin",
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.shift_type = create_shift_type(
            name="الفجر",
            start_time=time(4, 0),
            end_time=time(8, 0),
        )
        self.shift = create_shift_plan(
            shift_type=self.shift_type,
            shift_date=timezone.localdate(),
            start_time=time(4, 0),
            end_time=time(8, 0),
            is_active=True,
            is_finished=False,
        )
        self.url = reverse("scheduling:finish-shift", args=[self.shift.pk])

    def test_active_ready_and_finished_card_states(self):
        response = self.client.get(reverse("scheduling:status"))
        self.assertContains(
            response,
            f'data-finish-url="{self.url}"',
        )

        self.shift.is_active = False
        self.shift.save(update_fields=["is_active"])
        response = self.client.get(reverse("scheduling:status"))
        self.assertContains(response, f'data-shift-id="{self.shift.pk}"')
        self.assertNotContains(response, f'data-finish-url="{self.url}"')

        self.shift.is_finished = True
        self.shift.save(update_fields=["is_finished"])
        response = self.client.get(reverse("scheduling:status"))
        self.assertContains(response, "منتهية")
        self.assertNotContains(response, f'data-finish-url="{self.url}"')

    def test_counts_are_rendered_from_annotations(self):
        DoorShift.objects.create(
            shift_plan=self.shift,
            door_number="1",
            is_active=True,
        )
        DoorShift.objects.create(
            shift_plan=self.shift,
            door_number="2",
            is_active=False,
        )
        employee = create_employee()
        ShiftAssignment.objects.create(
            shift_plan=self.shift,
            employee=employee,
        )

        response = self.client.get(reverse("scheduling:status"))
        self.assertContains(response, 'data-active-door-count="1"')
        self.assertContains(response, 'data-assignment-count="1"')

    def test_get_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unauthorized_post_is_forbidden(self):
        user = create_user(username="finish-shift-unauthorized")
        self.client.force_login(user)
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_unauthorized_user_does_not_see_finish_button(self):
        request = RequestFactory().get(reverse("scheduling:status"))
        request.user = create_user(username="finish-shift-ui-unauthorized")
        shifts = type(self.shift).objects.filter(pk=self.shift.pk).annotate(
            active_door_count=Count(
                "door_shifts",
                filter=Q(door_shifts__is_active=True),
                distinct=True,
            ),
            assignment_count=Count("assignments", distinct=True),
        )
        html = render_to_string(
            "scheduling/shifts_status.html",
            {
                "shifts": shifts,
                "shift_types": [self.shift_type],
                "today": timezone.localdate(),
                "can_finish_shift": False,
            },
            request=request,
        )
        self.assertNotIn(f'data-finish-url="{self.url}"', html)

    def test_finish_creates_report_redirect_and_success_message(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        report = ShiftReport.objects.get(shift_plan=self.shift)
        self.assertEqual(
            payload["redirect_url"],
            reverse("reporting:detail", args=[report.pk]),
        )
        self.assertEqual(payload["message"], self.success_message)
        self.assertIn(
            self.success_message,
            [str(message) for message in get_messages(response.wsgi_request)],
        )
        self.shift.refresh_from_db()
        self.assertFalse(self.shift.is_active)
        self.assertTrue(self.shift.is_finished)

    def test_existing_report_is_reused(self):
        self.shift.is_active = False
        self.shift.is_finished = True
        self.shift.save(update_fields=["is_active", "is_finished"])
        report = ShiftReport.objects.create(
            report_type=ShiftReport.ReportType.OPERATIONAL,
            shift_plan=self.shift,
            created_by=self.user,
        )
        type(self.shift).objects.filter(pk=self.shift.pk).update(
            is_active=True,
            is_finished=False,
        )
        self.shift.refresh_from_db()
        with patch(
            "apps.scheduling.views.ReportService.generate_shift_report"
        ) as generate_report:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        generate_report.assert_not_called()
        self.assertEqual(ShiftReport.objects.count(), 1)
        self.assertEqual(
            response.json()["redirect_url"],
            reverse("reporting:detail", args=[report.pk]),
        )

    def test_view_uses_official_finish_service(self):
        with patch(
            "apps.scheduling.views.finish_shift",
            side_effect=official_finish_shift,
        ) as finish_service:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        finish_service.assert_called_once()
        self.assertEqual(finish_service.call_args.args[0].pk, self.shift.pk)

    def test_duplicate_finish_is_prevented(self):
        self.assertEqual(self.client.post(self.url).status_code, 200)
        with patch("apps.scheduling.views.finish_shift") as finish_service:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        finish_service.assert_not_called()
        self.assertEqual(ShiftReport.objects.count(), 1)

    def test_finish_validation_error_is_returned_without_report(self):
        with patch(
            "apps.scheduling.views.finish_shift",
            side_effect=ValidationError("تعذر إنهاء الوردية حاليًا."),
        ):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "تعذر إنهاء الوردية حاليًا.")
        self.assertFalse(ShiftReport.objects.exists())
        self.shift.refresh_from_db()
        self.assertTrue(self.shift.is_active)

    def test_report_failure_rolls_back_finish(self):
        with patch(
            "apps.scheduling.views.ReportService.generate_shift_report",
            side_effect=ValidationError("تعذر إنشاء التقرير."),
        ):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ShiftReport.objects.exists())
        self.shift.refresh_from_db()
        self.assertTrue(self.shift.is_active)
        self.assertFalse(self.shift.is_finished)
