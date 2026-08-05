from __future__ import annotations

from typing import Any

from django.core.files.base import ContentFile
from django.http import HttpRequest
from django.utils import timezone

from apps.exports_center.models import ExportLog


def create_processing_log(
    *,
    request: HttpRequest,
    module: str,
    report_key: str,
    file_name: str,
    export_format: str,
    filters: dict[str, Any],
) -> ExportLog:
    """
    إنشاء سجل تصدير بحالة قيد المعالجة.
    """
    forwarded_for = request.META.get(
        "HTTP_X_FORWARDED_FOR",
        "",
    )

    requested_ip = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else request.META.get("REMOTE_ADDR")
    )

    return ExportLog.objects.create(
        user=request.user,
        module=module,
        report_key=report_key,
        file_name=file_name,
        export_format=export_format,
        status=ExportLog.ExportStatus.PROCESSING,
        filters=filters,
        requested_ip=requested_ip or None,
        user_agent=request.META.get(
            "HTTP_USER_AGENT",
            "",
        )[:2000],
    )


def complete_export_log(
    *,
    export_log: ExportLog,
    content: bytes,
    records_count: int,
) -> None:
    """
    حفظ الملف وتحويل العملية إلى مكتملة.
    """
    export_log.file.save(
        export_log.file_name,
        ContentFile(content),
        save=False,
    )
    export_log.storage_path = export_log.file.name

    export_log.status = ExportLog.ExportStatus.SUCCESS
    export_log.records_count = max(
        int(records_count),
        0,
    )
    export_log.file_size = len(content)
    export_log.completed_at = timezone.now()
    export_log.error_message = ""

    export_log.save(
        update_fields=[
            "file",
            "file_name",
            "storage_path",
            "status",
            "records_count",
            "file_size",
            "completed_at",
            "error_message",
            "updated_at",
        ]
    )


def fail_export_log(
    *,
    export_log: ExportLog,
    exception: Exception,
) -> None:
    """
    تسجيل فشل إنشاء ملف التصدير.
    """
    export_log.status = ExportLog.ExportStatus.FAILED
    export_log.error_message = str(exception)[:5000]
    export_log.completed_at = timezone.now()

    export_log.save(
        update_fields=[
            "status",
            "error_message",
            "completed_at",
            "updated_at",
        ]
    )
