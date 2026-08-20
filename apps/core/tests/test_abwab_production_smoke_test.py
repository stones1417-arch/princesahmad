from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.breaks.models import Break
from apps.core.management.commands.abwab_production_smoke_test import Command
from apps.core.tests.factories import create_door, create_shift_plan, create_shift_type, create_zone
from apps.distribution.models import DoorAssignment
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.ops.models import DoorShift
from apps.scheduling.models import ShiftPlan
from apps.exports_center.services.shift_pdf_exporter import _render_pdf_bytes


class AbwabProductionSmokeTestCommandTests(TestCase):
    def test_shift_pdf_uses_server_renderer_without_playwright(self):
        html = (
            '<html lang="ar" dir="rtl"><body>'
            '<h1>التقرير التشغيلي للوردية</h1>'
            '<p>القسم التشغيلي — الأبواب 6A و6B</p>'
            '</body></html>'
        )
        with patch(
            "apps.exports_center.services.shift_pdf_exporter."
            "ReportService.render_pdf",
            return_value=b"%PDF-server-renderer",
        ) as render_pdf:
            content = _render_pdf_bytes(html)

        self.assertEqual(content[:4], b"%PDF")
        render_pdf.assert_called_once_with(html)

    def seed_master_doors(self):
        zone = create_zone(name="smoke-master-zone")
        return [
            create_door(door_number=code, zone=zone)
            for code in OFFICIAL_DOOR_CODES
        ]

    def run_execute(self, output=None):
        output = output or StringIO()
        with patch(
            "apps.exports_center.services.shift_pdf_exporter._render_pdf_bytes",
            return_value=b"%PDF-1.4\n%%EOF",
        ):
            try:
                call_command(
                    "abwab_production_smoke_test",
                    "--execute",
                    "--strict",
                    stdout=output,
                )
            except CommandError as error:
                self.fail(f"{error}\n{output.getvalue()}")
        return output.getvalue()

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
        self.seed_master_doors()
        create_shift_plan(
            shift_type=create_shift_type(name="active_smoke_shift"),
            shift_date="2026-08-17",
            is_active=True,
            is_finished=False,
        )
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("abwab_production_smoke_test", "--execute", "--strict", stdout=output)

        self.assertIn("ERROR_TYPE=ACTIVE_PRODUCTION_STATE", output.getvalue())

    @override_settings(DEBUG=True)
    def test_execute_successful_lifecycle_rolls_back_cleanly(self):
        self.seed_master_doors()
        output = StringIO()
        with patch("apps.core.tasks.send_sms_task.delay") as send_sms_delay, patch("apps.core.tasks.send_email_task.delay") as send_email_delay:
            self.run_execute(output)

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
        self.seed_master_doors()
        output = StringIO()
        call_command("abwab_production_smoke_test", "--dry-run", stdout=output)
        rendered = output.getvalue()
        self.assertIn("IMPORT_READY=PASS", rendered)
        self.assertIn("SMOKE_TEST_RESULT=PASS", rendered)

    def test_active_finished_shift_still_blocks_execute(self):
        self.seed_master_doors()
        create_shift_plan(is_active=False, is_finished=True)
        output = StringIO()
        with patch.object(ShiftPlan.objects, "filter") as shift_filter:
            shift_filter.return_value.count.return_value = 1
            with self.assertRaises(CommandError):
                call_command("abwab_production_smoke_test", "--execute", stdout=output)
        shift_filter.assert_any_call(is_active=True)
        self.assertIn("FAILED_STAGE=BASELINE", output.getvalue())
        self.assertIn("ERROR_TYPE=ACTIVE_PRODUCTION_STATE", output.getvalue())

    def test_active_door_shift_without_active_plan_blocks_execute(self):
        doors = self.seed_master_doors()
        shift = create_shift_plan(is_active=True, is_finished=False)
        DoorShift.objects.create(
            shift_plan=shift,
            door_number=doors[0].door_number,
            is_active=True,
        )
        ShiftPlan.objects.filter(pk=shift.pk).update(is_active=False)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("abwab_production_smoke_test", "--execute", stdout=output)
        self.assertIn("active DoorShift=1", output.getvalue())

    def test_active_gate_failure_performs_no_writes(self):
        self.seed_master_doors()
        create_shift_plan(is_active=True, is_finished=False)
        before = Command._snapshot_baseline()
        with self.assertRaises(CommandError):
            call_command("abwab_production_smoke_test", "--execute", stdout=StringIO())
        self.assertEqual(Command._snapshot_baseline(), before)

    def test_baseline_is_captured_before_master_door_read(self):
        baseline_seen = False
        original_snapshot = Command._snapshot_baseline

        def snapshot():
            nonlocal baseline_seen
            baseline_seen = True
            return original_snapshot()

        def master_doors():
            self.assertTrue(baseline_seen)
            return []

        with patch.object(Command, "_snapshot_baseline", side_effect=snapshot), patch.object(
            Command, "_master_doors", side_effect=master_doors
        ):
            with self.assertRaises(CommandError):
                call_command("abwab_production_smoke_test", "--execute", stdout=StringIO())

    def test_master_door_count_other_than_42_blocks_execute(self):
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("abwab_production_smoke_test", "--execute", stdout=output)
        self.assertIn("FAILED_STAGE=MASTER_DOORS", output.getvalue())

    def test_duplicate_master_door_code_is_rejected(self):
        codes = list(OFFICIAL_DOOR_CODES)
        codes[-1] = codes[0]
        ok, message = Command._validate_master_doors(
            [SimpleNamespace(door_number=code) for code in codes]
        )
        self.assertFalse(ok)
        self.assertIn("duplicate codes", message)

    def test_plain_six_is_rejected(self):
        codes = list(OFFICIAL_DOOR_CODES)
        codes[-1] = "6"
        ok, message = Command._validate_master_doors(
            [SimpleNamespace(door_number=code) for code in codes]
        )
        self.assertFalse(ok)
        self.assertIn("plain door 6 exists", message)

    def test_6a_and_6b_are_required(self):
        codes = [code for code in OFFICIAL_DOOR_CODES if code not in {"6A", "6B"}]
        ok, message = Command._validate_master_doors(
            [SimpleNamespace(door_number=code) for code in codes]
        )
        self.assertFalse(ok)
        self.assertIn("6A", message)
        self.assertIn("6B", message)

    def test_success_contract_includes_door_shift_sync_and_residue(self):
        self.seed_master_doors()
        rendered = self.run_execute()
        for line in (
            "42_DOORS=PASS",
            "6A_6B=PASS",
            "DATABASE_RESIDUE=0",
            "ROLLBACK_INTEGRITY=PASS",
        ):
            self.assertIn(line, rendered)

    def test_break_cycle_reuses_same_employee(self):
        self.seed_master_doors()
        seen_break_employee_ids = []
        original_assignment = Command._assignment

        def record_assignment(command, shift, employee, door, section, operator):
            if employee.full_name.endswith("_break"):
                seen_break_employee_ids.append(employee.pk)
            return original_assignment(command, shift, employee, door, section, operator)

        with patch.object(Command, "_assignment", new=record_assignment):
            self.run_execute()
        self.assertGreaterEqual(len(seen_break_employee_ids), 2)
        self.assertEqual(len(set(seen_break_employee_ids)), 1)

    def test_storage_upload_is_mocked_in_successful_lifecycle(self):
        self.seed_master_doors()
        self.assertIn("REAL_STORAGE_UPLOAD=NO", self.run_execute())

    def test_email_and_sms_are_reported_blocked(self):
        self.seed_master_doors()
        rendered = self.run_execute()
        self.assertIn("NO_REAL_EMAIL=PASS", rendered)
        self.assertIn("NO_REAL_SMS=PASS", rendered)

    def test_lifecycle_exception_still_runs_rollback_audits(self):
        self.seed_master_doors()
        output = StringIO()
        with patch.object(Command, "_run_lifecycle", side_effect=RuntimeError("safe failure")):
            with self.assertRaises(CommandError):
                call_command("abwab_production_smoke_test", "--execute", stdout=output)
        rendered = output.getvalue()
        self.assertIn("POST_ROLLBACK_BASELINE=PASS", rendered)
        self.assertIn("POST_ROLLBACK_RESIDUE=PASS", rendered)
        self.assertIn("DATABASE_RESIDUE=0", rendered)

    def test_failure_contract_prints_exact_failed_stage_and_safe_error(self):
        self.seed_master_doors()
        output = StringIO()
        with patch.object(Command, "_run_lifecycle", side_effect=ValueError("concise error")):
            with self.assertRaises(CommandError):
                call_command("abwab_production_smoke_test", "--execute", stdout=output)
        rendered = output.getvalue()
        self.assertIn("FULL_SHIFT_LIFECYCLE=FAIL", rendered)
        self.assertIn("FAILED_STAGE=TEST_SHIFT", rendered)
        self.assertIn("ERROR_TYPE=ValueError", rendered)
        self.assertIn("ERROR=concise error", rendered)
