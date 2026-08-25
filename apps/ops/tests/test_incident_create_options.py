from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
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
from apps.ops.engineering_center_service import EngineeringCenterService
from apps.roles.models import Role, UserRole
from apps.roles.services.role_manager import (
    assign_role_to_user,
    get_platform_permissions,
)
from apps.scheduling.models import ShiftAssignment
from apps.scheduling.operational_leadership_service import assign_shift_operational_leader


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

    def _engineering_post(self, door, **overrides):
        payload = {
            "door_id": str(door.pk),
            "description": "Engineering center incident",
            "incident_type": Incident.IncidentType.GENERAL,
            "priority": Incident.Priority.MEDIUM,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("ops:engineering-incident-create", args=[door.pk]), payload
        )

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
        self.assertIsNone(response.context["incident_supervisor"])

    def test_general_incident_without_door_is_supported(self):
        self.client.force_login(self.admin)

        response = self._post()

        self.assertEqual(response.status_code, 200)
        incident = Incident.objects.get(pk=response.json()["incident"]["id"])
        self.assertIsNone(incident.door_id)

    def test_general_form_keeps_selectable_door_catalog(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:incidents"))
        self.assertContains(response, 'id="incidentDoor"')
        self.assertContains(response, "بلاغ عام بدون باب")
        self.assertNotContains(response, "data-engineering-fixed-door")

    def test_engineering_context_renders_fixed_door_and_resets_between_doors(self):
        self.client.force_login(self.admin)
        door_1 = Door.objects.get(door_number="1")
        door_6b = Door.objects.get(door_number="6B")
        first = self.client.get(
            reverse("ops:incidents"), {"engineering_door": door_1.pk, "create": 1}
        )
        second = self.client.get(
            reverse("ops:incidents"), {"engineering_door": door_6b.pk, "create": 1}
        )
        self.assertContains(first, "الباب 1")
        self.assertContains(second, "الباب 6B")
        self.assertNotContains(second, "الباب 1")
        for response, door in ((first, door_1), (second, door_6b)):
            self.assertContains(response, "data-engineering-fixed-door")
            self.assertContains(response, f'name="door_id" value="{door.pk}"')
            self.assertContains(
                response,
                reverse("ops:engineering-incident-create", args=[door.pk]),
            )
            self.assertNotContains(response, 'id="incidentDoor"')

    def test_engineering_endpoint_uses_url_door_and_rejects_forgery(self):
        self.client.force_login(self.admin)
        source = Door.objects.get(door_number="2")
        other = Door.objects.get(door_number="3")
        forged = self._engineering_post(source, door_id=str(other.pk))
        self.assertEqual(forged.status_code, 400)
        forged_shift = self._engineering_post(source, door_shift_id="999999")
        self.assertEqual(forged_shift.status_code, 400)
        self.assertEqual(Incident.objects.count(), 0)
        created = self._engineering_post(source)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(Incident.objects.get().door_id, source.pk)

    def test_engineering_endpoint_blocks_inactive_and_cross_section_doors(self):
        inactive = Door.objects.get(door_number="41")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        self.client.force_login(self.admin)
        self.assertEqual(self._engineering_post(inactive).status_code, 404)
        self.client.force_login(self.actor)
        female = Door.objects.filter(
            operational_section=Door.OperationalSection.FEMALE
        ).first()
        self.assertEqual(self._engineering_post(female).status_code, 404)
        self.assertEqual(Incident.objects.count(), 0)

    def test_engineering_special_door_codes_are_authoritative(self):
        self.client.force_login(self.admin)
        for code in ("6A", "6B"):
            door = Door.objects.get(door_number=code)
            response = self._engineering_post(door)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                Incident.objects.get(pk=response.json()["incident"]["id"]).door,
                door,
            )
        self.assertFalse(Door.objects.filter(door_number="6").exists())

    def test_source_door_followup_and_metrics_receive_created_incident_only(self):
        self.client.force_login(self.admin)
        source = Door.objects.get(door_number="1")
        other = Door.objects.get(door_number="2")
        before = EngineeringCenterService.build(active_shift=self.shift)
        before_by_id = {item.door.pk: item for item in before["doors"]}
        response = self._engineering_post(source)
        incident_id = response.json()["incident"]["id"]
        after = EngineeringCenterService.build(active_shift=self.shift)
        after_by_id = {item.door.pk: item for item in after["doors"]}
        self.assertEqual(
            after_by_id[source.pk].open_incident_count,
            before_by_id[source.pk].open_incident_count + 1,
        )
        self.assertEqual(
            after_by_id[source.pk].today_incident_count,
            before_by_id[source.pk].today_incident_count + 1,
        )
        self.assertEqual(
            after_by_id[other.pk].open_incident_count,
            before_by_id[other.pk].open_incident_count,
        )
        source_payload = self.client.get(
            reverse("ops:door-incident-followup", args=[source.pk])
        ).json()
        other_payload = self.client.get(
            reverse("ops:door-incident-followup", args=[other.pk])
        ).json()
        self.assertIn(incident_id, [item["id"] for item in source_payload["incidents"]])
        self.assertNotIn(incident_id, [item["id"] for item in other_payload["incidents"]])

    def test_engineering_create_endpoint_requires_csrf(self):
        door = Door.objects.get(door_number="1")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        response = csrf_client.post(
            reverse("ops:engineering-incident-create", args=[door.pk]),
            {"door_id": door.pk, "description": "No CSRF token"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Incident.objects.count(), 0)

    def test_invalid_and_inactive_door_posts_are_rejected(self):
        self.client.force_login(self.admin)
        inactive = Door.objects.get(door_number="41")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        self.assertEqual(self._post(door_id="999999").status_code, 404)
        self.assertEqual(self._post(door_id=inactive.pk).status_code, 404)
        self.assertEqual(Incident.objects.count(), 0)

    def test_manual_assignee_selector_and_old_supervisor_copy_are_removed(self):
        self.client.force_login(self.actor)
        response = self.client.get(reverse("ops:incidents"))
        self.assertNotContains(response, 'id="assignedToName"')
        self.assertNotContains(response, "يُعيّن مشرف الوردية ثم النائب")
        self.assertContains(response, "لا يوجد مشرف بلاغات معيّن لهذه الوردية")

    def test_incident_center_presents_specialist_and_enterprise_contract(self):
        specialist = self._create_shift_responsible(
            username="center-incident-specialist", employee_number="CENTER-INC",
            section="male", role_code="incident_supervisor",
            assignment_role=ShiftAssignment.OperationalRole.SUPERVISOR,
        )
        assign_shift_operational_leader(
            shift_plan=self.shift, responsibility="incident_supervisor",
            employee=specialist.employee, actor=self.admin,
        )
        Incident.objects.create(
            shift_plan=self.shift, description="بلاغ واجهة المركز",
            created_by=self.admin, assigned_to=specialist,
            assigned_to_name=specialist.employee.full_name, section="male",
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:incidents"))
        for text in (
            "مركز البلاغات التشغيلية", "الجهة المالكة", "قيادة البلاغات الحالية",
            specialist.employee.full_name, "سيتم توجيه البلاغ تلقائيًا",
            "قيد المعالجة", "المصعّدة", "مرتبطة بالصيانة", "عرض التفاصيل",
        ):
            self.assertContains(response, text)
        self.assertContains(response, "incident_center.css")
        self.assertContains(response, "incident_center.js")

    def test_general_shift_supervisor_is_not_specialist_fallback(self):
        male_door = Door.objects.filter(operational_section="male").first()
        self.client.force_login(self.actor)

        supervisor_response = self._post(door_id=male_door.pk)

        self.assertEqual(supervisor_response.status_code, 200)
        self.assertIsNone(Incident.objects.get().assigned_to_id)

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

    def test_no_active_shift_creates_unassigned_incident(self):
        self.shift.is_active = False
        self.shift.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.admin)

        response = self._post(door_id=Door.objects.first().pk)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIsNone(Incident.objects.get().assigned_to_id)
