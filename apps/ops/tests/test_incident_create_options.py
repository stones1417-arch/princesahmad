from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_user,
    create_zone,
)
from apps.locations.models import Door
from apps.ops.models import Incident
from apps.roles.models import Role, UserRole
from apps.roles.services.role_manager import (
    assign_role_to_user,
    get_platform_permissions,
)
from apps.scheduling.models import ShiftAssignment


class IncidentCreateOptionsTests(TestCase):
    door_codes = [
        "1", "2", "3", "4", "5", "6B", "6A",
        *[str(number) for number in range(7, 42)],
    ]

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        zone = create_zone(name="Incident master catalog")
        for code in cls.door_codes:
            create_door(door_number=code, zone=zone)

        cls.shift = create_shift_plan(is_active=True)
        cls.supervisor = cls._create_shift_responsible(
            username="male-incident-supervisor",
            employee_number="INC-SUP-M",
            section="male",
            role_code="shift_supervisor",
            assignment_role=ShiftAssignment.OperationalRole.SHIFT_HEAD,
        )
        cls.deputy = cls._create_shift_responsible(
            username="male-incident-deputy",
            employee_number="INC-DEP-M",
            section="male",
            role_code="shift_deputy",
            assignment_role=ShiftAssignment.OperationalRole.SHIFT_DEPUTY,
        )
        cls.female_supervisor = cls._create_shift_responsible(
            username="female-incident-supervisor",
            employee_number="INC-SUP-F",
            section="female",
            role_code="shift_supervisor",
            assignment_role=ShiftAssignment.OperationalRole.SHIFT_HEAD,
        )
        cls.ordinary_user = create_user(username="ordinary-incident-employee")
        ordinary_employee = create_employee(
            user=cls.ordinary_user,
            employee_number="INC-ORD-M",
            operational_section="male",
        )
        ShiftAssignment.objects.create(
            shift_plan=cls.shift,
            employee=ordinary_employee,
            role=ShiftAssignment.OperationalRole.SHIFT_HEAD,
            is_confirmed=True,
        )
        cls.inactive_supervisor = cls._create_shift_responsible(
            username="inactive-incident-supervisor",
            employee_number="INC-INACTIVE-M",
            section="male",
            role_code="shift_supervisor",
            assignment_role=ShiftAssignment.OperationalRole.SHIFT_HEAD,
            user_active=False,
        )

        actor_group = Group.objects.create(name="incident-male-creator")
        actor_group.permissions.set(
            get_platform_permissions(["roles.view_doors", "roles.create_incident"])
        )
        actor_role = Role.objects.create(
            code="incident-male-creator",
            name="Incident male creator",
            group=actor_group,
            operational_section=Role.OperationalSection.MALE,
        )
        cls.actor = create_user(username="incident-male-actor")
        UserRole.objects.create(user=cls.actor, role=actor_role)
        cls.admin = create_user(username="incident-options-admin", is_superuser=True)

    @classmethod
    def _create_shift_responsible(
        cls,
        *,
        username,
        employee_number,
        section,
        role_code,
        assignment_role,
        user_active=True,
    ):
        user = create_user(username=username, is_active=user_active)
        employee = create_employee(
            user=user,
            employee_number=employee_number,
            operational_section=section,
        )
        assign_role_to_user(user=user, role_code=role_code)
        ShiftAssignment.objects.create(
            shift_plan=cls.shift,
            employee=employee,
            role=assignment_role,
            is_confirmed=True,
        )
        return user

    def _post(self, **overrides):
        payload = {
            "description": "بلاغ تشغيلي لاختبار خيارات الإنشاء",
            "incident_type": Incident.IncidentType.GENERAL,
            "priority": Incident.Priority.MEDIUM,
        }
        payload.update(overrides)
        return self.client.post(reverse("ops:incident-create"), payload)

    def test_master_door_catalog_is_available_in_official_order(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:incidents"))

        codes = [door.door_number for door in response.context["doors"]]
        self.assertEqual(codes, self.door_codes)
        self.assertEqual(len(codes), 42)
        self.assertNotIn("6", codes)
        self.assertEqual(codes[5:7], ["6B", "6A"])

    def test_inactive_door_is_excluded(self):
        Door.objects.filter(door_number="41").update(is_active=False)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("ops:incidents"))

        self.assertNotIn("41", [door.door_number for door in response.context["doors"]])

    def test_doors_remain_available_without_active_shift(self):
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.admin)

        response = self.client.get(reverse("ops:incidents"))

        self.assertEqual(len(response.context["doors"]), 42)
        self.assertEqual(list(response.context["incident_assignees"]), [])

    def test_general_incident_without_door_is_supported(self):
        self.client.force_login(self.admin)

        response = self._post()

        self.assertEqual(response.status_code, 200)
        incident = Incident.objects.get(pk=response.json()["incident"]["id"])
        self.assertIsNone(incident.door_id)

    def test_invalid_and_inactive_door_posts_are_rejected(self):
        self.client.force_login(self.admin)
        inactive = Door.objects.get(door_number="41")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        self.assertEqual(self._post(door_id="999999").status_code, 404)
        self.assertEqual(self._post(door_id=inactive.pk).status_code, 404)
        self.assertEqual(Incident.objects.count(), 0)

    def test_only_active_shift_responsibles_in_actor_section_are_visible(self):
        self.client.force_login(self.actor)

        response = self.client.get(reverse("ops:incidents"))

        user_ids = {
            assignment.employee.user_id
            for assignment in response.context["incident_assignees"]
        }
        self.assertIn(self.supervisor.pk, user_ids)
        self.assertIn(self.deputy.pk, user_ids)
        self.assertNotIn(self.female_supervisor.pk, user_ids)
        self.assertNotIn(self.ordinary_user.pk, user_ids)
        self.assertNotIn(self.inactive_supervisor.pk, user_ids)

    def test_valid_supervisor_and_deputy_can_receive_male_door_incident(self):
        male_door = Door.objects.filter(operational_section="male").first()
        self.client.force_login(self.actor)

        supervisor_response = self._post(
            door_id=male_door.pk,
            assigned_to_id=self.supervisor.pk,
        )
        deputy_response = self._post(
            door_id=male_door.pk,
            assigned_to_id=self.deputy.pk,
        )

        self.assertEqual(supervisor_response.status_code, 200)
        self.assertEqual(deputy_response.status_code, 200)
        self.assertEqual(
            set(Incident.objects.values_list("assigned_to_id", flat=True)),
            {self.supervisor.pk, self.deputy.pk},
        )

    def test_forged_ordinary_and_cross_section_assignees_are_rejected(self):
        male_door = Door.objects.filter(operational_section="male").first()
        self.client.force_login(self.actor)

        ordinary_response = self._post(
            door_id=male_door.pk,
            assigned_to_id=self.ordinary_user.pk,
        )
        cross_section_response = self._post(
            door_id=male_door.pk,
            assigned_to_id=self.female_supervisor.pk,
        )

        self.assertEqual(ordinary_response.status_code, 400)
        self.assertEqual(cross_section_response.status_code, 400)
        self.assertEqual(Incident.objects.count(), 0)

    def test_no_active_shift_fails_safely_without_creating_incident(self):
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.admin)

        response = self._post(door_id=Door.objects.first().pk)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(Incident.objects.count(), 0)
