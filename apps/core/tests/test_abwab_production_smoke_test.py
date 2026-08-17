from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.breaks.models import Break
from apps.distribution.models import DoorAssignment
from apps.ops.models import DoorShift
from apps.scheduling.models import ShiftPlan


class AbwabProductionSmokeTestCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_loads_and_dry_run_is_read_only(self):
        output = StringIO()
        before_counts = {
            "ShiftPlan": ShiftPlan.objects.count(),
            "DoorShift": DoorShift.objects.count(),
            "DoorAssignment": DoorAssignment.objects.count(),
            "Break": Break.objects.count(),
        }

        call_command("abwab_production_smoke_test", "--dry-run", stdout=output)

        rendered = output.getvalue()
        self.assertIn("PRECHECK=PASS", rendered)
        self.assertIn("MIGRATIONS=PASS", rendered)
        self.assertIn("DRY_RUN_READ_ONLY=PASS", rendered)
        self.assertEqual(ShiftPlan.objects.count(), before_counts["ShiftPlan"])
        self.assertEqual(DoorShift.objects.count(), before_counts["DoorShift"])
        self.assertEqual(DoorAssignment.objects.count(), before_counts["DoorAssignment"])
        self.assertEqual(Break.objects.count(), before_counts["Break"])

    @override_settings(DEBUG=True)
    def test_execute_rejects_active_residue_before_any_write(self):
        from apps.core.tests.factories import create_shift_plan, create_shift_type

        create_shift_plan(
            shift_type=create_shift_type(name="active_smoke_shift"),
            shift_date="2026-08-17",
            is_active=True,
            is_finished=False,
        )
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("abwab_production_smoke_test", "--execute", "--strict", stdout=output)

        self.assertIn("active ShiftPlan count > 0", str(output.getvalue()) or "")

    @override_settings(DEBUG=True)
    def test_execute_successful_lifecycle_rolls_back_cleanly(self):
        output = StringIO()
        with patch("apps.core.tasks.send_sms_task.delay") as send_sms_delay, patch("apps.core.tasks.send_email_task.delay") as send_email_delay:
            call_command("abwab_production_smoke_test", "--execute", "--strict", stdout=output)

        rendered = output.getvalue()
        self.assertIn("FULL_SHIFT_LIFECYCLE=PASS", rendered)
        self.assertIn("READY_FOR_NEXT_RELEASE_STAGE=YES", rendered)
        self.assertIn("NO_REAL_EMAIL=PASS", rendered)
        self.assertIn("NO_REAL_SMS=PASS", rendered)
        send_sms_delay.assert_not_called()
        send_email_delay.assert_not_called()
        self.assertEqual(ShiftPlan.objects.count(), 0)
        self.assertEqual(DoorShift.objects.count(), 0)
        self.assertEqual(DoorAssignment.objects.count(), 0)
        self.assertEqual(Break.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_missing_migrations_fail_dry_run_precheck(self):
        output = StringIO()
        with patch("apps.core.management.commands.abwab_production_smoke_test.MigrationExecutor.migration_plan", return_value=[object()]):
            with self.assertRaises(CommandError):
                call_command("abwab_production_smoke_test", "--execute", "--strict", stdout=output)

    @override_settings(DEBUG=True)
    def test_dry_run_reports_failed_migration_precheck_without_crashing(self):
        output = StringIO()
        with patch("apps.core.management.commands.abwab_production_smoke_test.MigrationExecutor.migration_plan", return_value=[object()]):
            result = call_command("abwab_production_smoke_test", "--dry-run", stdout=output)

        self.assertIsNone(result)
        rendered = output.getvalue()
        self.assertIn("MIGRATIONS=FAIL", rendered)
        self.assertIn("pending migrations", rendered)

    @override_settings(DEBUG=True)
    def test_dry_run_uses_import_readiness_and_reports_pass(self):
        output = StringIO()
        call_command("abwab_production_smoke_test", "--dry-run", stdout=output)
        rendered = output.getvalue()
        self.assertIn("IMPORT_READY=PASS", rendered)
        self.assertIn("SMOKE_TEST_RESULT=PASS", rendered)
