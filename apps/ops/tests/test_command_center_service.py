from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ops.command_center_service import (
    CommandCenterService,
)


class CommandCenterIndicatorsTests(SimpleTestCase):
    """
    اختبارات حساب مؤشرات غرفة القيادة.
    """

    def test_percentage_calculation(self):
        self.assertEqual(
            CommandCenterService._percentage(
                5,
                10,
            ),
            50,
        )

    def test_percentage_returns_zero_without_total(self):
        self.assertEqual(
            CommandCenterService._percentage(
                5,
                0,
            ),
            0,
        )

    def test_readiness_rate_counts_open_and_secured(self):
        metrics = SimpleNamespace(
            total_doors=10,
            open_doors=6,
            secured_doors=2,
        )

        result = (
            CommandCenterService
            ._calculate_readiness_rate(
                metrics=metrics,
            )
        )

        self.assertEqual(
            result,
            80,
        )

    def test_supervision_coverage(self):
        metrics = SimpleNamespace(
            total_doors=10,
            doors_without_supervisor=2,
        )

        result = (
            CommandCenterService
            ._calculate_supervision_coverage(
                metrics=metrics,
            )
        )

        self.assertEqual(
            result,
            80,
        )

    def test_monitor_coverage(self):
        metrics = SimpleNamespace(
            total_doors=10,
            doors_without_monitor=3,
        )

        result = (
            CommandCenterService
            ._calculate_monitor_coverage(
                metrics=metrics,
            )
        )

        self.assertEqual(
            result,
            70,
        )

    def test_operational_score_without_penalties(self):
        score = (
            CommandCenterService
            ._calculate_operational_score(
                readiness_rate=100,
                supervision_coverage_rate=100,
                monitor_coverage_rate=100,
                critical_incidents=0,
                open_maintenance=0,
            )
        )

        self.assertEqual(
            score,
            100,
        )

    def test_critical_incident_reduces_score(self):
        score = (
            CommandCenterService
            ._calculate_operational_score(
                readiness_rate=100,
                supervision_coverage_rate=100,
                monitor_coverage_rate=100,
                critical_incidents=1,
                open_maintenance=0,
            )
        )

        self.assertEqual(
            score,
            88,
        )

    def test_maintenance_penalty_is_limited(self):
        score = (
            CommandCenterService
            ._calculate_operational_score(
                readiness_rate=100,
                supervision_coverage_rate=100,
                monitor_coverage_rate=100,
                critical_incidents=0,
                open_maintenance=100,
            )
        )

        self.assertEqual(
            score,
            80,
        )

    def test_score_never_falls_below_zero(self):
        score = (
            CommandCenterService
            ._calculate_operational_score(
                readiness_rate=0,
                supervision_coverage_rate=0,
                monitor_coverage_rate=0,
                critical_incidents=20,
                open_maintenance=20,
            )
        )

        self.assertEqual(
            score,
            0,
        )

    def test_stable_status_for_high_score(self):
        key, label = (
            CommandCenterService
            ._get_operational_status(
                score=90,
                critical_incidents=0,
            )
        )

        self.assertEqual(
            key,
            "stable",
        )

        self.assertEqual(
            label,
            "التشغيل مستقر",
        )

    def test_warning_status_for_medium_score(self):
        key, label = (
            CommandCenterService
            ._get_operational_status(
                score=70,
                critical_incidents=0,
            )
        )

        self.assertEqual(
            key,
            "warning",
        )

        self.assertEqual(
            label,
            "يحتاج متابعة",
        )

    def test_critical_incident_forces_critical_status(self):
        key, label = (
            CommandCenterService
            ._get_operational_status(
                score=100,
                critical_incidents=1,
            )
        )

        self.assertEqual(
            key,
            "critical",
        )

        self.assertEqual(
            label,
            "حالة حرجة",
        )


class CommandCenterDirectionMetricsTests(SimpleTestCase):
    """
    اختبارات مؤشرات الجهات.
    """

    def test_direction_metrics_are_calculated(self):
        groups = [
            {
                "key": "south",
                "label": "الجهة الجنوبية",
                "doors": [
                    {
                        "state": "open",
                        "employee_count": 2,
                        "open_incident_count": 1,
                        "open_maintenance_count": 0,
                        "supervisor_assignment": object(),
                    },
                    {
                        "state": "maintenance",
                        "employee_count": 1,
                        "open_incident_count": 0,
                        "open_maintenance_count": 1,
                        "supervisor_assignment": None,
                    },
                    {
                        "state": "secured",
                        "employee_count": 2,
                        "open_incident_count": 0,
                        "open_maintenance_count": 0,
                        "supervisor_assignment": object(),
                    },
                ],
            },
        ]

        result = (
            CommandCenterService
            ._build_direction_metrics(
                groups=groups,
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        direction = result[0]

        self.assertEqual(
            direction["total_doors"],
            3,
        )

        self.assertEqual(
            direction["open_doors"],
            1,
        )

        self.assertEqual(
            direction["maintenance_doors"],
            1,
        )

        self.assertEqual(
            direction["secured_doors"],
            1,
        )

        self.assertEqual(
            direction["employees"],
            5,
        )

        self.assertEqual(
            direction["incidents"],
            1,
        )

        self.assertEqual(
            direction["maintenance_requests"],
            1,
        )

        self.assertEqual(
            direction["without_supervisor"],
            1,
        )

        self.assertEqual(
            direction["readiness_rate"],
            67,
        )