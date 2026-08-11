from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.monitoring import (
    collect_monitoring_snapshot,
    emit_critical_alerts,
)


class Command(BaseCommand):
    help = "Collect post-release signals and emit critical alerts."

    def handle(self, *args, **options):
        snapshot = collect_monitoring_snapshot()
        emit_critical_alerts(snapshot)
        self.stdout.write(json.dumps(snapshot, ensure_ascii=False, default=str))
        if snapshot["alerts"]:
            raise CommandError("Critical monitoring thresholds were exceeded.")