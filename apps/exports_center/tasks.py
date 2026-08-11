from __future__ import annotations

import logging

from celery import shared_task

from apps.exports_center.models import ExportLog
from apps.exports_center.services.export_logger import (
    complete_export_log,
    fail_export_log,
)
from apps.exports_center.services.export_service import export_report


logger = logging.getLogger("platform.exports")


@shared_task
def build_export_file_task(export_log_id: int) -> dict[str, int | str]:
    """Generate a stored export from its durable audit record."""
    export_log = (
        ExportLog.objects.select_related("user")
        .filter(pk=export_log_id)
        .first()
    )
    if not export_log:
        logger.warning(
            "Export log no longer exists.",
            extra={
                "event": "export_missing",
                "export_log_id": export_log_id,
                "task_name": "build_export_file_task",
            },
        )
        return {"status": "missing", "export_log_id": export_log_id}

    if export_log.status == ExportLog.ExportStatus.SUCCESS:
        return {"status": "success", "export_log_id": export_log.pk}

    export_log.mark_processing()

    try:
        result = export_report(
            report_key=export_log.report_key,
            export_format=export_log.export_format,
            filters=export_log.filters,
            user=export_log.user,
            selected_columns=(
                export_log.metadata.get("selected_columns")
                if isinstance(export_log.metadata, dict)
                else None
            ),
            allow_empty=True,
        )
        export_log.file_name = result.file_name
        complete_export_log(
            export_log=export_log,
            content=result.content,
            records_count=result.records_count,
        )
    except Exception as error:
        logger.exception(
            "Asynchronous export failed.",
            extra={
                "event": "export_failed",
                "export_log_id": export_log.pk,
                "report_key": export_log.report_key,
                "task_name": "build_export_file_task",
            },
        )
        fail_export_log(export_log=export_log, exception=error)
        raise

    logger.info(
        "Asynchronous export completed.",
        extra={
            "event": "export_completed",
            "export_log_id": export_log.pk,
            "report_key": export_log.report_key,
            "task_name": "build_export_file_task",
        },
    )

    return {"status": "success", "export_log_id": export_log.pk}