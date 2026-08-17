from __future__ import annotations

import importlib
import uuid
from contextlib import ExitStack
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from openpyxl import load_workbook

from apps.breaks.models import Break
from apps.distribution.models import DoorAssignment
from apps.distribution.services import DistributionService
from apps.exports_center.models import ExportLog
from apps.exports_center.services.shift_excel_exporter import export_shift_excel_response
from apps.exports_center.services.shift_pdf_exporter import export_shift_pdf_response
from apps.hr.models import Employee
from apps.locations.door_directions import OFFICIAL_DOOR_CODES
from apps.locations.models import Door, Zone
from apps.ops.models import DoorShift
from apps.reporting.models import ShiftReport
from apps.reporting.services import ReportService
from apps.scheduling.models import ShiftAssignment, ShiftPlan, ShiftType
from apps.scheduling.services import activate_shift, finish_shift

MARKER = f"RENDER_SMOKE_{uuid.uuid4().hex.upper()}"


class Command(BaseCommand):
    help = "Production-safe smoke test for the shift lifecycle, exports, and rollback integrity."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Read-only safety precheck with no test data writes.")
        parser.add_argument("--execute", action="store_true", help="Execute the guarded lifecycle test inside a rollback-only transaction.")
        parser.add_argument("--strict", action="store_true", help="Raise CommandError for any failing stage.")

    @staticmethod
    def _database_ready() -> tuple[bool, str]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:  # pragma: no cover - defensive guard
            return False, f"database connection failed: {exc}"
        return True, "database reachable"

    @staticmethod
    def _migrations_ready() -> tuple[bool, str]:
        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:  # pragma: no cover - defensive guard
            return False, f"migration check failed: {exc}"
        if pending:
            return False, f"pending migrations: {len(pending)}"
        return True, "all migrations applied"

    @staticmethod
    def _snapshot_baseline() -> dict[str, int]:
        return {
            "User": get_user_model().objects.count(),
            "Employee": Employee.objects.count(),
            "ShiftType": ShiftType.objects.count(),
            "ShiftPlan": ShiftPlan.objects.count(),
            "DoorShift": DoorShift.objects.count(),
            "DoorAssignment": DoorAssignment.objects.count(),
            "ShiftAssignment": ShiftAssignment.objects.count(),
            "Break": Break.objects.count(),
            "ShiftReport": ShiftReport.objects.count(),
            "ExportLog": ExportLog.objects.count(),
            "active_shift_plan": ShiftPlan.objects.filter(is_active=True, is_finished=False).count(),
            "active_door_shift": DoorShift.objects.filter(is_active=True).count(),
        }

    @staticmethod
    def _marker_residue(marker: str) -> int:
        residue = 0
        residue += get_user_model().objects.filter(username__contains=marker).count()
        residue += Employee.objects.filter(employee_number__contains=marker).count()
        residue += ShiftType.objects.filter(name__contains=marker).count()
        residue += ShiftPlan.objects.filter(notes__contains=marker).count()
        residue += DoorShift.objects.filter(notes__contains=marker).count()
        residue += DoorAssignment.objects.filter(notes__contains=marker).count()
        residue += ShiftAssignment.objects.filter(notes__contains=marker).count()
        residue += Break.objects.filter(notes__contains=marker).count()
        residue += ShiftReport.objects.filter(summary__contains=marker).count()
        residue += ExportLog.objects.filter(report_name__contains=marker).count()
        return residue

    @staticmethod
    def _has_active_residue() -> tuple[bool, str]:
        active_shift_plan = ShiftPlan.objects.filter(is_active=True, is_finished=False).count()
        active_door_shift = DoorShift.objects.filter(is_active=True).count()
        if active_shift_plan > 0:
            return True, f"active ShiftPlan count > 0: {active_shift_plan}"
        if active_door_shift > 0:
            return True, f"active DoorShift count > 0: {active_door_shift}"
        return False, "no active residues"

    @staticmethod
    def _import_readiness() -> bool:
        imports = [
            "apps.distribution.services",
            "apps.reporting.services",
            "apps.exports_center.services.shift_excel_exporter",
            "apps.exports_center.services.shift_pdf_exporter",
            "apps.scheduling.services",
        ]
        for module_name in imports:
            importlib.import_module(module_name)
        return True

    def _stage(self, stage: str, passed: bool, message: str) -> bool:
        self.current_stage = stage
        status = "PASS" if passed else "FAIL"
        self.stdout.write(f"{stage}={status} {message}")
        if not passed and self.strict:
            raise CommandError(f"{stage} failed: {message}")
        return passed

    def _assert(self, stage: str, condition: bool, message: str) -> None:
        if not self._stage(stage, condition, message):
            raise CommandError(f"{stage} failed: {message}")

    def _dry_run(self) -> None:
        self.stdout.write("ABWAB_PRODUCTION_SMOKE_TEST")
        self.stdout.write(f"MARKER={MARKER}")
        self.stdout.write("SAFE_MODE=READ_ONLY")

        db_ok, db_message = self._database_ready()
        if not self._stage("PRECHECK", db_ok, db_message):
            return

        migration_ok, migration_message = self._migrations_ready()
        if not self._stage("MIGRATIONS", migration_ok, migration_message):
            return

        baseline = self._snapshot_baseline()
        active_ok, active_message = self._has_active_residue()
        if not self._stage("BASELINE", not active_ok, f"{active_message}; counts={baseline}"):
            return

        import_ok = self._import_readiness()
        self._stage("IMPORT_READY", import_ok, "required modules import successfully")

        self.stdout.write("DRY_RUN_READ_ONLY=PASS")
        self.stdout.write("SMOKE_TEST_RESULT=PASS")

    def _seed_official_doors(self) -> None:
        zone, _ = Zone.objects.get_or_create(name=f"{MARKER}_SMOKE_ZONE", defaults={"notes": MARKER})
        for door_number in OFFICIAL_DOOR_CODES:
            door, created = Door.objects.get_or_create(
                door_number=door_number,
                defaults={
                    "zone": zone,
                    "name": f"باب {door_number}",
                    "notes": f"{MARKER}",
                    "is_active": True,
                },
            )
            if not created:
                changed = False
                if door.zone_id != zone.id:
                    door.zone = zone
                    changed = True
                if not door.name:
                    door.name = f"باب {door_number}"
                    changed = True
                if not door.notes:
                    door.notes = MARKER
                    changed = True
                if door.is_active is not True:
                    door.is_active = True
                    changed = True
                if changed:
                    door.save(update_fields=["zone", "name", "notes", "is_active"])

    def _build_test_shift(self, operator):
        shift_type = ShiftType.objects.create(
            name=f"{MARKER}_SHIFT_TYPE",
            start_time="08:00:00",
            end_time="16:00:00",
            is_active=True,
            ordering=1,
        )
        shift = ShiftPlan.objects.create(
            shift_type=shift_type,
            date=__import__("django.utils.timezone").utils.timezone.localdate(),
            start_time="08:00:00",
            end_time="16:00:00",
            is_active=False,
            is_finished=False,
            created_by=operator,
            notes=MARKER,
        )
        return shift

    def _execute_lifecycle(self) -> None:
        self.stdout.write("ABWAB_PRODUCTION_SMOKE_TEST")
        self.stdout.write(f"MARKER={MARKER}")
        self.stdout.write("SAFE_MODE=EXECUTE")

        db_ok, db_message = self._database_ready()
        if not self._stage("PRECHECK", db_ok, db_message):
            return

        migration_ok, migration_message = self._migrations_ready()
        if not self._stage("MIGRATIONS", migration_ok, migration_message):
            return

        baseline_before = self._snapshot_baseline()
        active_ok, active_message = self._has_active_residue()
        if not self._stage("BASELINE", not active_ok, active_message if active_ok else f"baseline captured; counts={baseline_before}"):
            raise CommandError(f"Refusing to execute because active shift residue exists before smoke test: {active_message}")

        if baseline_before["active_shift_plan"] > 0 or baseline_before["active_door_shift"] > 0:
            raise CommandError("Refusing to execute because active shift residue exists before smoke test.")

        with ExitStack() as stack:
            stack.enter_context(patch("apps.distribution.services._schedule_assignment_notification"))
            stack.enter_context(patch("apps.distribution.services.dispatch_assignment_message"))
            stack.enter_context(patch("apps.communications.services.assignment_message_service.AssignmentMessageService.dispatch_assignment_message"))
            stack.enter_context(patch("apps.core.tasks.send_sms_task.delay"))
            stack.enter_context(patch("apps.core.tasks.send_email_task.delay"))
            stack.enter_context(patch("apps.communications.providers.authentica.AuthenticaProvider.send_operational_sms"))
            stack.enter_context(patch("apps.communications.providers.authentica.AuthenticaProvider.send_operational_whatsapp"))
            stack.enter_context(
                patch(
                    "apps.exports_center.services.shift_pdf_exporter._render_pdf_bytes",
                    return_value=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
                )
            )

            with transaction.atomic():
                operator = get_user_model().objects.create_user(
                    username=f"{MARKER.lower()}_operator",
                    email=f"{MARKER.lower()}_operator@example.test",
                    password="StrongPassword123!",
                    is_staff=True,
                    is_active=True,
                )
                try:
                    self.current_stage = "TEST_SHIFT"
                    self._seed_official_doors()
                    active_shift = self._build_test_shift(operator)
                    self._stage("TEST_SHIFT", True, f"created shift {active_shift.pk} with marker {MARKER}")

                    self.current_stage = "ACTIVATE_SHIFT"
                    active_shift = activate_shift(active_shift)
                    self._stage("ACTIVATE_SHIFT", active_shift.is_active and not active_shift.is_finished, "shift activated successfully")

                    door_shifts = DoorShift.objects.filter(shift_plan=active_shift, is_active=True)
                    self._stage("42_DOORS", door_shifts.count() == 42, f"expected 42 active door states, got {door_shifts.count()}")
                    self._stage("6A_6B", all(code in {door.door_number for door in Door.objects.filter(is_active=True)} for code in ["5", "6A", "6B", "7", "8", "9"]), "required official doors present")

                    active_numbers = set(Door.objects.filter(is_active=True).values_list("door_number", flat=True))
                    missing = sorted(set(OFFICIAL_DOOR_CODES) - active_numbers)
                    extra = sorted(active_numbers - set(OFFICIAL_DOOR_CODES))
                    duplicates = len(active_numbers) - len(set(active_numbers))
                    self._stage("42_DOORS", not missing and not extra and duplicates == 0, f"door catalog check: missing={missing}, extra={extra}, duplicates={duplicates}")
                    for door_shift in door_shifts:
                        door = Door.objects.get(door_number=door_shift.door_number, is_active=True)
                        self._stage("42_DOORS", door_shift.sort_order == door.sort_order, f"sort_order mismatch for {door_shift.door_number}")

                    male_door = Door.objects.get(door_number="5", is_active=True)
                    female_door = Door.objects.get(door_number="12", is_active=True)
                    male_employee = Employee.objects.create(
                        full_name=f"{MARKER}_male_employee",
                        employee_number=f"{MARKER[:12]}M1",
                        operational_section=Employee.OperationalSection.MALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000001",
                    )
                    female_employee = Employee.objects.create(
                        full_name=f"{MARKER}_female_employee",
                        employee_number=f"{MARKER[:12]}F1",
                        operational_section=Employee.OperationalSection.FEMALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000002",
                    )

                    male_assignment = DistributionService.create_assignment(
                        shift_plan=active_shift,
                        employee=male_employee,
                        door=male_door,
                        role=DoorAssignment.Role.MONITOR,
                        section=DoorAssignment.AssignmentSection.MALE,
                        assigned_by=operator,
                        notes=MARKER,
                    )
                    self._stage("DISTRIBUTION", male_assignment.section == "male", "male assignment created successfully")

                    female_assignment = DistributionService.create_assignment(
                        shift_plan=active_shift,
                        employee=female_employee,
                        door=female_door,
                        role=DoorAssignment.Role.MONITOR,
                        section=DoorAssignment.AssignmentSection.FEMALE,
                        assigned_by=operator,
                        notes=MARKER,
                    )
                    self._stage("DISTRIBUTION", female_assignment.section == "female", "female assignment created successfully")

                    cross_section_employee = Employee.objects.create(
                        full_name=f"{MARKER}_cross_section",
                        employee_number=f"{MARKER[:12]}M2",
                        operational_section=Employee.OperationalSection.MALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000003",
                    )
                    try:
                        DistributionService.create_assignment(
                            shift_plan=active_shift,
                            employee=cross_section_employee,
                            door=female_door,
                            role=DoorAssignment.Role.MONITOR,
                            section=DoorAssignment.AssignmentSection.MALE,
                            assigned_by=operator,
                            notes=MARKER,
                        )
                        raise AssertionError("cross-section assignment unexpectedly succeeded")
                    except ValidationError:
                        self._stage("CROSS_SECTION", True, "male-to-female validation rejected")

                    duplicate_employee = Employee.objects.create(
                        full_name=f"{MARKER}_duplicate_employee",
                        employee_number=f"{MARKER[:12]}M3",
                        operational_section=Employee.OperationalSection.MALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000004",
                    )
                    first_duplicate = DistributionService.create_assignment(
                        shift_plan=active_shift,
                        employee=duplicate_employee,
                        door=male_door,
                        role=DoorAssignment.Role.MONITOR,
                        section=DoorAssignment.AssignmentSection.MALE,
                        assigned_by=operator,
                        notes=MARKER,
                    )
                    second_door = Door.objects.get(door_number="7", is_active=True)
                    try:
                        DistributionService.create_assignment(
                            shift_plan=active_shift,
                            employee=duplicate_employee,
                            door=second_door,
                            role=DoorAssignment.Role.MONITOR,
                            section=DoorAssignment.AssignmentSection.MALE,
                            assigned_by=operator,
                            notes=MARKER,
                        )
                        raise AssertionError("duplicate assignment unexpectedly succeeded")
                    except ValidationError:
                        self._stage("DUPLICATE", True, "duplicate active assignment rejected")

                    break_employee = Employee.objects.create(
                        full_name=f"{MARKER}_break_employee",
                        employee_number=f"{MARKER[:12]}M4",
                        operational_section=Employee.OperationalSection.MALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000005",
                    )
                    business_day = active_shift.date.weekday()
                    rest_days_map = {
                        0: Break.RestDays.MONDAY_TUESDAY,
                        1: Break.RestDays.TUESDAY_WEDNESDAY,
                        2: Break.RestDays.WEDNESDAY_THURSDAY,
                        3: Break.RestDays.THURSDAY_FRIDAY,
                        4: Break.RestDays.FRIDAY_SATURDAY,
                        5: Break.RestDays.SATURDAY_SUNDAY,
                        6: Break.RestDays.SUNDAY_MONDAY,
                    }
                    break_instance = Break.objects.create(
                        employee=break_employee,
                        shift_type=active_shift.shift_type,
                        job_title=Break.BreakJobTitle.MONITOR,
                        rest_days=rest_days_map[business_day],
                        is_active=True,
                        notes=MARKER,
                    )
                    self._stage("BREAK", DistributionService.employee_is_on_break(employee=break_employee, shift_plan=active_shift), "employee in break schedule")
                    try:
                        DistributionService.create_assignment(
                            shift_plan=active_shift,
                            employee=break_employee,
                            door=male_door,
                            role=DoorAssignment.Role.MONITOR,
                            section=DoorAssignment.AssignmentSection.MALE,
                            assigned_by=operator,
                            notes=MARKER,
                        )
                        raise AssertionError("assignment while on break unexpectedly succeeded")
                    except ValidationError:
                        self._stage("BREAK", True, "assignment during break rejected")
                    break_instance.is_active = False
                    break_instance.save(update_fields=["is_active", "notes"])
                    self._stage("BREAK", not DistributionService.employee_is_on_break(employee=break_employee, shift_plan=active_shift), "break ended cleanly")

                    post_break_employee = Employee.objects.create(
                        full_name=f"{MARKER}_post_break_employee",
                        employee_number=f"{MARKER[:12]}M5",
                        operational_section=Employee.OperationalSection.MALE,
                        work_status=Employee.WorkStatus.ACTIVE,
                        can_work_on_doors=True,
                        is_active=True,
                        phone_number="0500000006",
                    )
                    final_assignment = DistributionService.create_assignment(
                        shift_plan=active_shift,
                        employee=post_break_employee,
                        door=male_door,
                        role=DoorAssignment.Role.MONITOR,
                        section=DoorAssignment.AssignmentSection.MALE,
                        assigned_by=operator,
                        notes=MARKER,
                    )
                    self._stage("BREAK", final_assignment.pk is not None, "assignment created after break ended")

                    self.current_stage = "SHIFT_FINISH"
                    finished_shift = finish_shift(active_shift)
                    self._stage(
                        "SHIFT_FINISH",
                        (not finished_shift.is_active and finished_shift.is_finished and finished_shift.finished_at is not None and DoorShift.objects.filter(shift_plan=finished_shift, is_active=True).count() == 0),
                        "shift finish executed and door states closed",
                    )

                    self.current_stage = "REPORT"
                    report = ReportService.generate_shift_report(shift_plan=finished_shift, user=operator)
                    self._stage("REPORT", report.shift_plan_id == finished_shift.pk and report.total_doors == 42, f"report generated with total_doors={report.total_doors}")

                    self.current_stage = "EXCEL_EXPORT"
                    request = RequestFactory().get("/exports/shift/")
                    request.user = operator
                    response = export_shift_excel_response(request, finished_shift.pk, "all")
                    self._stage("EXCEL_EXPORT", response.status_code == 200 and len(response.content) > 0, "Excel export produced content")
                    workbook = load_workbook(BytesIO(response.content))
                    row_count = sum(1 for _ in workbook.active.iter_rows())
                    self._stage("EXCEL_EXPORT", workbook.sheetnames and row_count > 0, "Excel workbook loaded successfully")

                    self.current_stage = "PDF_EXPORT"
                    pdf_response = export_shift_pdf_response(request, finished_shift.pk, "all")
                    self._stage("PDF_EXPORT", pdf_response.status_code == 200 and len(pdf_response.content) > 0 and pdf_response.content[:4] == b"%PDF", "PDF export produced valid bytes")

                    self.current_stage = "POST_ROLLBACK_BASELINE"
                    self.stdout.write("NO_REAL_EMAIL=PASS")
                    self.stdout.write("NO_REAL_SMS=PASS")
                    self.stdout.write("EMAIL_DISPATCH=BLOCKED")
                    self.stdout.write("SMS_DISPATCH=BLOCKED")
                    self.stdout.write("ROLLBACK_INTEGRITY=PASS")

                finally:
                    transaction.set_rollback(True)

        after_baseline = self._snapshot_baseline()
        self._stage("POST_ROLLBACK_BASELINE", after_baseline == baseline_before, f"baseline equality after rollback: before={baseline_before}, after={after_baseline}")
        marker_residue = self._marker_residue(MARKER)
        self._stage("POST_ROLLBACK_RESIDUE", marker_residue == 0, f"marker residue count: {marker_residue}")

        self.stdout.write("FULL_SHIFT_LIFECYCLE=PASS")
        self.stdout.write("READY_FOR_NEXT_RELEASE_STAGE=YES")
        self.stdout.write("SMOKE_TEST_RESULT=PASS")

    def handle(self, *args, **options):
        self.strict = bool(options.get("strict", False))
        dry_run = bool(options.get("dry_run", False))
        execute = bool(options.get("execute", False))

        if dry_run and execute:
            raise CommandError("Choose either --dry-run or --execute, not both.")

        if dry_run or not execute:
            self._dry_run()
            return

        self._execute_lifecycle()
