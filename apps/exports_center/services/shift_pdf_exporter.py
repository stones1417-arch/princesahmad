from __future__ import annotations

from urllib.parse import quote

from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string

from apps.exports_center.models import ExportLog
from apps.reporting.services import ReportService

from .export_logger import (
    complete_export_log,
    create_processing_log,
    fail_export_log,
)
from .shift_data_service import (
    get_shift_export_data,
    get_shift_records_count,
)


def _render_pdf_bytes(html: str) -> bytes:
    """
    تحويل HTML إلى PDF عبر المحرك الخادمي المؤسسي المشترك.
    """
    return ReportService.render_pdf(html)


def export_shift_pdf_response(
    request: HttpRequest,
    shift_plan_id: int,
    section: str,
) -> HttpResponse:
    """
    إنشاء ملف PDF لتقرير وردية محددة.
    """
    data = get_shift_export_data(
        shift_plan_id=shift_plan_id,
    )

    shift_plan = data["shift_plan"]

    shift_name = (
        shift_plan.shift_type.name
        if shift_plan.shift_type
        else f"shift_{shift_plan.pk}"
    )

    file_name = (
        f"shift_"
        f"{shift_name}_"
        f"{shift_plan.date}_"
        f"{section}.pdf"
    ).replace(" ", "_")

    export_log = create_processing_log(
        request=request,
        module=f"تقرير وردية {shift_name}",
        report_key="shift_bundle",
        file_name=file_name,
        export_format=ExportLog.ExportFormat.PDF,
        filters={
            "shift_plan": shift_plan.pk,
            "section": section,
        },
    )

    try:
        html = render_to_string(
            "exports_center/pdf/shift_bundle.html",
            {
                **data,
                "section": section,
            },
            request=request,
        )

        content = _render_pdf_bytes(html)

        records_count = get_shift_records_count(
            data=data,
            section=section,
        )

        complete_export_log(
            export_log=export_log,
            content=content,
            records_count=records_count,
        )

        response = HttpResponse(
            content,
            content_type="application/pdf",
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{file_name}"; '
            f"filename*=UTF-8''{quote(file_name)}"
        )

        response["Content-Length"] = str(len(content))

        return response

    except Exception as exc:
        fail_export_log(
            export_log=export_log,
            exception=exc,
        )
        raise
