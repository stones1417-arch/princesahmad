from io import StringIO
from unittest.mock import patch
from datetime import time, timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.hr.models import Employee
from apps.locations.models import Door, Zone
from apps.notifications.models import Notification
from apps.ops.management.commands._full_operations_demo import MARKER
from apps.ops.models import (DoorOperationalProfile, Incident, IncidentRoutingEvent,
                             IncidentSupervisoryAction, LeadershipDelegation,
                             MaintenanceRequest)
from apps.ops.engineering_center_service import EngineeringCenterService
from apps.ops.operations_center_service import OperationsCenterService
from apps.ops.supervisory_leadership_service import SupervisoryLeadershipService
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.scheduling.models import ShiftAssignment, ShiftPlan, ShiftType


@override_settings(DEBUG=True)
class FullOperationsDemoCommandsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ShiftType.objects.create(name="Official test shift", start_time=time(6), end_time=time(14), ordering=1)
        zone = Zone.objects.create(name="Demo command test zone", notes="test fixture")
        for index in range(1, 5):
            door = Door.objects.create(
                door_number=str(index), name=f"Test door {index}", zone=zone,
                operational_section=Door.OperationalSection.MALE, sort_order=index,
            )
            DoorOperationalProfile.objects.create(
                door=door, target_staff_count=2 if index == 2 else 1,
            )

    def test_seed_is_idempotent_validate_run_and_delete_are_scoped(self):
        output = StringIO()
        call_command("seed_full_operations_demo", stdout=output)
        call_command("seed_full_operations_demo", stdout=output)
        call_command("validate_full_operations_demo", stdout=output)

        self.assertEqual(Employee.objects.filter(notes__contains=MARKER).count(), 55)
        self.assertEqual(ShiftPlan.objects.filter(notes__contains=MARKER).count(), 1)
        self.assertFalse(any(employee.user.has_usable_password() for employee in Employee.objects.filter(notes__contains=MARKER).select_related("user")))

        call_command("run_full_operations_demo", scenario="full-cycle", stdout=output)
        call_command("run_full_operations_demo", scenario="full-cycle", stdout=output)
        self.assertEqual(Incident.objects.filter(description__contains=MARKER).count(), 1)
        self.assertEqual(MaintenanceRequest.objects.filter(description__contains=MARKER).count(), 1)
        self.assertEqual(LeadershipDelegation.objects.filter(reason__contains=MARKER).count(), 1)
        incident = Incident.objects.get(description__contains=MARKER)
        maintenance = MaintenanceRequest.objects.get(source_incident=incident)
        self.assertNotEqual(incident.status, Incident.Status.CLOSED)
        self.assertEqual(maintenance.status, MaintenanceRequest.Status.DONE)
        self.assertIsNotNone(maintenance.started_at)
        self.assertIsNotNone(maintenance.fixed_at)
        self.assertEqual(incident.assigned_to.username, "abwab_demo_staff_03")
        self.assertEqual(incident.escalation_level, Incident.EscalationLevel.GENERAL_MANAGER)
        expected_actions = {
            IncidentSupervisoryAction.ActionType.REQUEST_UPDATE,
            IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE,
            IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_NOTE,
            IncidentSupervisoryAction.ActionType.ADMINISTRATIVE_ALERT,
            IncidentSupervisoryAction.ActionType.SUPERVISORY_NOTE,
            IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE,
        }
        self.assertTrue(expected_actions.issubset(set(incident.supervisory_actions.values_list("action_type", flat=True))))
        update_request = incident.supervisory_actions.get(action_type=IncidentSupervisoryAction.ActionType.REQUEST_UPDATE)
        self.assertEqual(update_request.status, IncidentSupervisoryAction.Status.RESOLVED)
        self.assertEqual(update_request.responses.count(), 1)
        self.assertEqual(update_request.responses.get().parent_id, update_request.pk)
        for action_type in (IncidentSupervisoryAction.ActionType.SUPERVISORY_DIRECTIVE, IncidentSupervisoryAction.ActionType.EXECUTIVE_DIRECTIVE):
            self.assertEqual(incident.supervisory_actions.get(action_type=action_type).status, IncidentSupervisoryAction.Status.COMPLETED)
        deputy_action = incident.supervisory_actions.get(actor__username="abwab_demo_staff_07")
        self.assertEqual(deputy_action.acting_for.username, "abwab_demo_staff_06")
        event_types = set(incident.routing_events.values_list("event_type", flat=True))
        self.assertTrue({
            IncidentRoutingEvent.EventType.CREATED,
            IncidentRoutingEvent.EventType.ASSIGNED,
            IncidentRoutingEvent.EventType.PROCESSING_STARTED,
            IncidentRoutingEvent.EventType.ESCALATED,
            IncidentRoutingEvent.EventType.CONVERTED_TO_MAINTENANCE,
            IncidentRoutingEvent.EventType.MAINTENANCE_APPROVED,
            IncidentRoutingEvent.EventType.MAINTENANCE_STARTED,
            IncidentRoutingEvent.EventType.MAINTENANCE_COMPLETED,
        }.issubset(event_types))
        self.assertTrue(Notification.objects.filter(user__username__startswith="abwab_demo_staff_").exists())
        duplicate = (Notification.objects.filter(user__username__startswith="abwab_demo_staff_")
                     .values("user_id", "title", "message").annotate(total=models.Count("pk")).filter(total__gt=1))
        self.assertFalse(duplicate.exists())
        shift = ShiftPlan.objects.get(notes__contains=MARKER)
        engineering = EngineeringCenterService.build(active_shift=shift, allowed_sections=["male"])
        self.assertEqual(engineering["summary"]["assigned_employees"], 46)
        coverage_levels = [row.staff_coverage_level for row in engineering["doors"]]
        self.assertGreaterEqual(coverage_levels.count("complete"), 1)
        self.assertGreaterEqual(sum(level in {"partial", "low"} for level in coverage_levels), 1)
        self.assertGreaterEqual(coverage_levels.count("uncovered"), 1)
        operations = OperationsCenterService.build()
        self.assertEqual(operations["active_shift"], shift)
        center_contracts = (
            ("abwab_demo_staff_01", reverse("scheduling:current"), shift.shift_type.name),
            ("abwab_demo_staff_03", reverse("ops:command-center"), incident.incident_number),
            ("abwab_demo_staff_03", reverse("ops:incidents"), incident.incident_number),
            ("abwab_demo_staff_04", reverse("ops:operations-center"), maintenance.request_number),
            ("abwab_demo_staff_05", reverse("ops:maintenance-list"), maintenance.request_number),
            ("abwab_demo_staff_06", reverse("ops:department-command-center"), incident.incident_number),
            ("abwab_demo_staff_08", reverse("ops:administrative-command-center"), incident.incident_number),
            ("abwab_demo_staff_09", reverse("ops:executive-command-center"), incident.incident_number),
            ("abwab_demo_staff_07", reverse("ops:department-command-center"), incident.incident_number),
        )
        for username, route, visible_text in center_contracts:
            self.client.force_login(Employee.objects.get(user__username=username).user)
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, (username, route))
            self.assertContains(response, visible_text)
        closer = Employee.objects.get(user__username="abwab_demo_staff_03").user
        self.assertTrue(user_has_permission(closer, PlatformPermissions.CLOSE_INCIDENT))
        for username in ("abwab_demo_staff_04", "abwab_demo_staff_05", "abwab_demo_staff_06", "abwab_demo_staff_07", "abwab_demo_staff_08", "abwab_demo_staff_09"):
            self.assertFalse(user_has_permission(
                Employee.objects.get(user__username=username).user,
                PlatformPermissions.CLOSE_INCIDENT,
            ))
        delegation = LeadershipDelegation.objects.get(reason__contains=MARKER)
        self.assertIsNotNone(SupervisoryLeadershipService.active_delegation(delegation.delegate, "male"))
        SupervisoryLeadershipService.revoke_delegation(delegation, delegation.principal)
        self.assertIsNone(SupervisoryLeadershipService.active_delegation(delegation.delegate, "male"))

        call_command("run_full_operations_demo", scenario="full-cycle", stop_before_final_close=False, stdout=output)
        incident.refresh_from_db()
        self.assertEqual(incident.status, Incident.Status.CLOSED)
        self.assertEqual(incident.closed_by.username, "abwab_demo_staff_03")

        ordinary = Employee.objects.create(employee_number="REAL-001", full_name="Real employee", notes="not demo")
        unsafe_incident = Incident.objects.create(
            section="male", description="Real incident must survive",
            created_by=Employee.objects.get(employee_number="DEMO-OPS-001").user,
        )
        with self.assertRaisesMessage(CommandError, "DELETE_SAFETY_BLOCKED"):
            call_command("delete_full_operations_demo", confirm=True, stdout=output)
        unsafe_incident.delete()
        call_command("delete_full_operations_demo", confirm=True, stdout=output)
        self.assertTrue(Employee.objects.filter(pk=ordinary.pk).exists())
        self.assertFalse(Employee.objects.filter(notes__contains=MARKER).exists())
        call_command("delete_full_operations_demo", confirm=True, stdout=output)

    def test_dry_run_rolls_back(self):
        call_command("seed_full_operations_demo", dry_run=True, stdout=StringIO())
        self.assertFalse(Employee.objects.filter(notes__contains=MARKER).exists())

    def test_count_extends_55_to_100_and_second_run_creates_zero(self):
        call_command("seed_full_operations_demo", stdout=StringIO())
        self.assertEqual(get_user_model().objects.filter(username__startswith="abwab_demo_staff_").count(), 55)

        output = StringIO()
        call_command("seed_full_operations_demo", count=100, stdout=output)
        self.assertIn("NEW_USERS_CREATED=45", output.getvalue())
        self.assertEqual(Employee.objects.filter(notes__contains=MARKER).count(), 100)
        self.assertEqual(ShiftAssignment.objects.filter(employee__notes__contains=MARKER).count(), 100)
        shift = ShiftPlan.objects.get(notes__contains=MARKER)
        self.assertEqual(ShiftAssignment.objects.filter(
            shift_plan=shift,
            role__in=(ShiftAssignment.OperationalRole.SHIFT_HEAD, ShiftAssignment.OperationalRole.SHIFT_DEPUTY),
        ).count(), 2)
        self.assertEqual(Employee.objects.filter(notes__contains=MARKER, can_execute_maintenance=True).count(), 6)
        coverage = EngineeringCenterService.build(active_shift=shift, allowed_sections=["male"])["doors"]
        self.assertGreaterEqual(sum(row.staff_coverage_level in {"complete", "surplus"} for row in coverage), 2)
        self.assertGreaterEqual(sum(row.staff_coverage_level in {"partial", "low"} for row in coverage), 1)
        self.assertGreaterEqual(sum(row.staff_coverage_level == "uncovered" for row in coverage), 1)

        output = StringIO()
        call_command("seed_full_operations_demo", count=100, stdout=output)
        self.assertIn("NEW_USERS_CREATED=0", output.getvalue())
        self.assertIn("NEW_EMPLOYEES_CREATED=0", output.getvalue())
        self.assertIn("NEW_SHIFT_ASSIGNMENTS_CREATED=0", output.getvalue())
        call_command("validate_full_operations_demo", strict=True, expected_count=100, stdout=StringIO())

    def test_use_current_shift_resolves_today_and_does_not_create_shift(self):
        call_command("seed_full_operations_demo", stdout=StringIO())
        demo = ShiftPlan.objects.get(notes__contains=MARKER)
        demo.is_active = False
        demo.save()
        current = ShiftPlan.objects.create(
            shift_type=ShiftType.objects.first(), date=timezone.localdate(),
            start_time=time(6), end_time=time(14), is_active=True, notes="real current shift",
        )
        shift_count = ShiftPlan.objects.count()
        output = StringIO()
        call_command("seed_full_operations_demo", count=100, use_current_shift=True, stdout=output)
        self.assertEqual(ShiftPlan.objects.count(), shift_count)
        self.assertEqual(ShiftAssignment.objects.filter(shift_plan=current, employee__notes__contains=MARKER).count(), 100)
        self.assertIn(f"CURRENT_SHIFT_ID={current.pk}", output.getvalue())

    def test_use_current_shift_blocks_when_missing_or_wrong_date(self):
        with self.assertRaisesMessage(CommandError, "NO_ACTIVE_SHIFT"):
            call_command("seed_full_operations_demo", use_current_shift=True, stdout=StringIO())
        wrong = ShiftPlan.objects.create(
            shift_type=ShiftType.objects.first(), date=timezone.localdate() + timedelta(days=1),
            start_time=time(6), end_time=time(14), is_active=True,
        )
        with self.assertRaisesMessage(CommandError, "WRONG_DATE_OR_INACTIVE_SHIFT"):
            call_command("seed_full_operations_demo", use_current_shift=True, stdout=StringIO())
        self.assertFalse(Employee.objects.filter(notes__contains=MARKER).exists())
        wrong.delete()

    def test_count_dry_run_reports_delta_without_writes(self):
        output = StringIO()
        call_command("seed_full_operations_demo", count=100, dry_run=True, stdout=output)
        self.assertIn("TARGET_USERS=100", output.getvalue())
        self.assertIn("NEW_USERS_TO_CREATE=100", output.getvalue())
        self.assertFalse(Employee.objects.filter(notes__contains=MARKER).exists())

    @override_settings(DEBUG=False)
    def test_production_requires_two_explicit_flags(self):
        with self.assertRaises(CommandError):
            call_command("seed_full_operations_demo", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("delete_full_operations_demo", stdout=StringIO())

    @override_settings(DEBUG=False)
    def test_production_refuses_demo_shift_beside_real_active_shift(self):
        shift_type = ShiftType.objects.create(name="Real active type", start_time=time(1), end_time=time(2), ordering=88)
        ShiftPlan.objects.create(shift_type=shift_type, date=timezone.localdate(), start_time=time(1), end_time=time(2), is_active=True, notes="real")
        with self.assertRaisesMessage(CommandError, "PRODUCTION_DEMO_SHIFT_UNSAFE"):
            call_command("seed_full_operations_demo", allow_production_demo=True, confirm_demo_seed=True, stdout=StringIO())

    def test_delete_requires_confirmation_outside_production_too(self):
        with self.assertRaises(CommandError):
            call_command("delete_full_operations_demo", stdout=StringIO())

    def test_validate_only_is_read_only(self):
        with self.assertRaises(CommandError):
            call_command("run_full_operations_demo", validate_only=True, stdout=StringIO())
        self.assertFalse(Employee.objects.filter(notes__contains=MARKER).exists())

    def test_optional_login_requires_environment_password(self):
        with self.assertRaises(CommandError):
            call_command("seed_full_operations_demo", enable_demo_logins=True, stdout=StringIO())
        output = StringIO()
        with patch.dict("os.environ", {"DEMO_WORKFORCE_PASSWORD": "Demo-only-password-938!"}):
            call_command("seed_full_operations_demo", enable_demo_logins=True, stdout=output)
        user = Employee.objects.get(employee_number="DEMO-OPS-001").user
        self.assertTrue(user.check_password("Demo-only-password-938!"))
        self.assertNotIn("Demo-only-password-938!", output.getvalue())

    def test_baseline_and_supervisory_modes_are_resumable(self):
        output = StringIO()
        call_command("seed_full_operations_demo", stdout=output)
        call_command("run_full_operations_demo", scenario="baseline", stdout=output)
        self.assertFalse(Incident.objects.filter(description__contains=MARKER).exists())
        call_command("run_full_operations_demo", scenario="supervisory", stdout=output)
        action_count = IncidentSupervisoryAction.objects.filter(note__contains=MARKER).count()
        call_command("run_full_operations_demo", scenario="supervisory", stdout=output)
        self.assertEqual(IncidentSupervisoryAction.objects.filter(note__contains=MARKER).count(), action_count)
