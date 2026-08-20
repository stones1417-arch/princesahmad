from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    create_door,
    create_employee,
    create_shift_plan,
    create_zone,
)
from apps.distribution.models import DoorAssignment
from apps.exports_center.models import ExportLog
from apps.exports_center.registry import REPORT_REGISTRY, SUPPORTED_EXPORT_FORMATS
from apps.exports_center.selectors import (
    SELECTOR_REGISTRY,
    door_distribution_selector,
    locations_selector,
)
from apps.roles.models import Role, UserRole
from apps.roles.services.permission_registry import PlatformPermissions


class FinalExportCenterClosureTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="final-export-closure"
        )
        group = Group.objects.create(name="final-export-closure")
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="roles",
                codename="export_report",
            )
        )
        role = Role.objects.create(
            code="final-export-closure",
            name="Final export closure",
            group=group,
            operational_section=Role.OperationalSection.ALL,
        )
        UserRole.objects.create(user=self.user, role=role)
        self.client.force_login(self.user)

    def test_every_registered_definition_has_complete_contract(self):
        self.assertEqual(len(REPORT_REGISTRY), 9)

        for report_key, report in REPORT_REGISTRY.items():
            with self.subTest(report_key=report_key):
                self.assertEqual(report.key, report_key)
                self.assertTrue(report.title)
                self.assertIn(report.selector_key, SELECTOR_REGISTRY)
                self.assertEqual(
                    report.permission,
                    PlatformPermissions.EXPORT_REPORT,
                )
                self.assertTrue(report.supported_formats)
                self.assertTrue(
                    set(report.supported_formats).issubset(
                        SUPPORTED_EXPORT_FORMATS
                    )
                )
                self.assertTrue(report.columns)

                self.assertEqual(
                    reverse(
                        "exports_center:filters",
                        kwargs={"report_key": report_key},
                    ),
                    f"/exports/report/{report_key}/filters/",
                )
                self.assertEqual(
                    reverse(
                        "exports_center:preview",
                        kwargs={"report_key": report_key},
                    ),
                    f"/exports/report/{report_key}/preview/",
                )

    def test_route_methods_and_preview_side_effect_contract(self):
        initial_log_count = ExportLog.objects.count()

        for report_key, report in REPORT_REGISTRY.items():
            for route_name in ("filters", "preview", "preview-data"):
                with self.subTest(report_key=report_key, route=route_name):
                    response = self.client.get(
                        reverse(
                            f"exports_center:{route_name}",
                            kwargs={"report_key": report_key},
                        )
                    )
                    self.assertEqual(response.status_code, 200)

            for export_format in report.supported_formats:
                with self.subTest(
                    report_key=report_key,
                    export_format=export_format,
                ):
                    response = self.client.get(
                        reverse(
                            "exports_center:export",
                            kwargs={
                                "report_key": report_key,
                                "export_format": export_format,
                            },
                        )
                    )
                    self.assertEqual(response.status_code, 405)

        self.assertEqual(ExportLog.objects.count(), initial_log_count)

    def test_door_exports_follow_master_sort_order(self):
        zone = create_zone(name="Export ordering")
        doors = [
            create_door(door_number=code, zone=zone)
            for code in ("7", "6A", "5", "6B")
        ]
        self.assertEqual(
            list(locations_selector({}).values_list("door_number", flat=True)),
            ["5", "6B", "6A", "7"],
        )

        shift_plan = create_shift_plan(is_active=True)
        for index, door in enumerate(doors, start=1):
            employee = create_employee(
                employee_number=f"export-order-{index}",
                operational_section="male",
            )
            DoorAssignment.objects.create(
                shift_plan=shift_plan,
                door=door,
                employee=employee,
                section=DoorAssignment.AssignmentSection.MALE,
                role=DoorAssignment.Role.MONITOR,
                is_active=True,
            )

        self.assertEqual(
            list(
                door_distribution_selector({}).values_list(
                    "door__door_number", flat=True
                )
            ),
            ["5", "6B", "6A", "7"],
        )
