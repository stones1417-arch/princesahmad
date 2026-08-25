from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.role_permissions import ROLE_PERMISSIONS_BY_CODE
from apps.core.tests.factories import create_employee, create_shift_plan, create_user
from apps.dashboard.models import SystemActivityLog
from apps.ops.incident_routing_service import IncidentRoutingService
from apps.ops.models import Incident
from apps.roles.services.role_manager import assign_role_to_user
from apps.scheduling.models import ShiftAssignment, ShiftOperationalLeadership
from apps.scheduling.operational_leadership_service import (
    assign_shift_operational_leader,
    remove_shift_operational_leader,
)


class ShiftOperationalLeadershipTests(TestCase):
    def setUp(self):
        self.actor = create_user(username="leadership-admin", is_superuser=True)
        self.shift = create_shift_plan(is_active=True, is_finished=False)

    def member(self, responsibility, section="male"):
        user = create_user()
        employee = create_employee(
            user=user, operational_section=section, is_active=True,
        )
        assign_role_to_user(
            user=user, role_code=responsibility, assigned_by=self.actor
        )
        ShiftAssignment.objects.create(
            shift_plan=self.shift, employee=employee,
            role=ShiftAssignment.OperationalRole.SUPERVISOR, is_confirmed=True,
        )
        return employee

    def assign(self, responsibility, employee):
        return assign_shift_operational_leader(
            shift_plan=self.shift, responsibility=responsibility,
            employee=employee, actor=self.actor,
        )

    def test_three_roles_are_distinct_and_least_privilege(self):
        incident = ROLE_PERMISSIONS_BY_CODE["incident_supervisor"].permissions
        operations = ROLE_PERMISSIONS_BY_CODE["operations_supervisor"].permissions
        maintenance = ROLE_PERMISSIONS_BY_CODE["maintenance_shift_supervisor"].permissions
        self.assertIn("roles.change_door_coverage_settings", incident)
        self.assertNotIn("roles.assign_employees", incident)
        self.assertIn("roles.approve_maintenance_request", operations)
        self.assertNotIn("roles.close_maintenance_request", operations)
        self.assertIn("roles.close_maintenance_request", maintenance)
        self.assertNotIn("roles.approve_maintenance_request", maintenance)
        self.assertNotIn("roles.close_incident", maintenance)

    def test_assignment_validates_role_membership_and_uniqueness(self):
        employee = self.member("incident_supervisor")
        assignment = self.assign("incident_supervisor", employee)
        self.assertEqual(assignment.employee, employee)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ShiftOperationalLeadership.objects.create(
                shift_plan=self.shift, responsibility="incident_supervisor",
                employee=employee,
            )
        self.assertTrue(SystemActivityLog.objects.filter(
            module="القيادة التشغيلية للوردية"
        ).exists())

    def test_removal_is_audited(self):
        employee = self.member("incident_supervisor")
        self.assign("incident_supervisor", employee)
        self.assertTrue(remove_shift_operational_leader(
            shift_plan=self.shift, responsibility="incident_supervisor",
            actor=self.actor,
        ))
        self.assertFalse(ShiftOperationalLeadership.objects.filter(
            shift_plan=self.shift, responsibility="incident_supervisor"
        ).exists())
        self.assertTrue(SystemActivityLog.objects.filter(
            action=SystemActivityLog.ActionType.DELETE
        ).exists())

    def test_role_mismatch_and_nonmember_are_blocked(self):
        wrong = self.member("operations_supervisor")
        with self.assertRaises(ValidationError):
            self.assign("incident_supervisor", wrong)
        outsider_user = create_user(username="specialist-outsider")
        outsider = create_employee(user=outsider_user, operational_section="male")
        assign_role_to_user(
            user=outsider_user, role_code="incident_supervisor", assigned_by=self.actor
        )
        with self.assertRaises(ValidationError):
            self.assign("incident_supervisor", outsider)

    def test_invalid_responsibility_and_ordinary_actor_are_blocked(self):
        employee = self.member("incident_supervisor")
        with self.assertRaises(ValidationError):
            self.assign("forged", employee)
        ordinary = create_user(username="ordinary-leadership-actor")
        with self.assertRaises(PermissionDenied):
            assign_shift_operational_leader(
                shift_plan=self.shift, responsibility="incident_supervisor",
                employee=employee, actor=ordinary,
            )

    def test_incident_routes_to_specialist_and_preserves_assignee_on_escalation(self):
        employee = self.member("incident_supervisor")
        self.assign("incident_supervisor", employee)
        incident = Incident.objects.create(
            shift_plan=self.shift, section="male", description="بلاغ تخصصي",
            created_by=self.actor,
        )
        IncidentRoutingService.route_created_incident(incident, actor=self.actor)
        incident.refresh_from_db()
        self.assertEqual(incident.assigned_to, employee.user)

    def test_no_incident_supervisor_is_safe_without_fallback(self):
        incident = Incident.objects.create(
            shift_plan=self.shift, section="male", description="بلاغ دون مسؤول",
            created_by=self.actor,
        )
        IncidentRoutingService.route_created_incident(incident, actor=self.actor)
        incident.refresh_from_db()
        self.assertIsNone(incident.assigned_to)

    def test_four_shift_plans_support_twelve_assignments_with_three_roles(self):
        shifts = [self.shift]
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        for offset in range(1, 4):
            shifts.append(create_shift_plan(
                date=timezone.localdate() + timedelta(days=offset),
                is_active=False, is_finished=False,
            ))
        for index, shift in enumerate(shifts):
            self.shift = shift
            for responsibility, _label in ShiftOperationalLeadership.Responsibility.choices:
                employee = self.member(responsibility, section="male")
                self.assign(responsibility, employee)
        self.assertEqual(ShiftOperationalLeadership.objects.count(), 12)
