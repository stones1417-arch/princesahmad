from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from apps.exports_center.models import ExportLog
from apps.exports_center.registry import (
    FORMAT_CSV,
    FORMAT_EXCEL,
    FORMAT_PDF,
    REPORT_REGISTRY,
    get_report_choices,
    get_report_definition,
)
from apps.exports_center.services.export_service import (
    EmptyExportError,
    ExportServiceError,
    ReportFormatNotSupportedError,
    UnsupportedExportFormatError,
    export_report,
    preview_report,
)
from apps.exports_center.services.export_logger import (
    complete_export_log,
    create_processing_log,
    fail_export_log,
)


# ==================================================
# الثوابت
# ==================================================

DEFAULT_REPORT_KEY = "employees"
DEFAULT_PREVIEW_LIMIT = 50
MAX_PREVIEW_LIMIT = 200

FORMAT_LABELS = {
    FORMAT_EXCEL: "Excel",
    FORMAT_PDF: "PDF",
    FORMAT_CSV: "CSV",
}

FORMAT_ICONS = {
    FORMAT_EXCEL: "📊",
    FORMAT_PDF: "📄",
    FORMAT_CSV: "📋",
}


# ==================================================
# أدوات مساعدة
# ==================================================

def _get_report_or_404(
    report_key: str,
):
    """
    جلب تعريف التقرير أو إرجاع 404.
    """

    try:
        return get_report_definition(
            report_key
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise Http404(
            "التقرير المطلوب غير موجود."
        ) from exc


def _normalize_report_key(
    report_key: str | None,
) -> str:
    """
    تنظيف مفتاح التقرير.
    """

    normalized_key = (
        str(
            report_key
            or DEFAULT_REPORT_KEY
        )
        .strip()
        .lower()
    )

    if normalized_key not in REPORT_REGISTRY:
        return DEFAULT_REPORT_KEY

    return normalized_key


def _normalize_export_format(
    export_format: str | None,
) -> str:
    """
    تنظيف صيغة التصدير.
    """

    normalized_format = (
        str(
            export_format
            or FORMAT_EXCEL
        )
        .strip()
        .lower()
    )

    aliases = {
        "xlsx": FORMAT_EXCEL,
        "xls": FORMAT_EXCEL,
        "excel": FORMAT_EXCEL,
        "pdf": FORMAT_PDF,
        "csv": FORMAT_CSV,
    }

    return aliases.get(
        normalized_format,
        normalized_format,
    )


def _normalize_preview_limit(
    value: Any,
) -> int:
    """
    ضبط عدد سجلات المعاينة.
    """

    try:
        limit = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        limit = DEFAULT_PREVIEW_LIMIT

    return max(
        1,
        min(
            limit,
            MAX_PREVIEW_LIMIT,
        ),
    )


def _extract_filters(
    request: HttpRequest,
) -> dict[str, Any]:
    """
    استخراج فلاتر التقرير من GET أو POST.

    يتم حذف الحقول الخاصة بالواجهة
    وعدم إرسالها إلى selectors.py.
    """

    source = (
        request.POST
        if request.method == "POST"
        else request.GET
    )

    ignored_keys = {
        "csrfmiddlewaretoken",
        "report_key",
        "export_format",
        "format",
        "action",
        "preview_limit",
        "submit",
        "page",
    }

    filters: dict[str, Any] = {}

    for key in source.keys():
        if key in ignored_keys:
            continue

        values = [
            value.strip()
            if isinstance(
                value,
                str,
            )
            else value
            for value in source.getlist(
                key
            )
            if value not in (
                None,
                "",
            )
        ]

        if not values:
            continue

        filters[key] = (
            values[0]
            if len(values) == 1
            else values
        )

    return filters


def _build_report_cards() -> list[dict[str, Any]]:
    """
    تجهيز بطاقات التقارير للوحة المركز.
    """

    cards: list[dict[str, Any]] = []

    for report_key, report in (
        REPORT_REGISTRY.items()
    ):
        supported_formats = []

        for export_format in (
            FORMAT_EXCEL,
            FORMAT_PDF,
            FORMAT_CSV,
        ):
            if report.supports_format(
                export_format
            ):
                supported_formats.append(
                    {
                        "key": export_format,
                        "label": FORMAT_LABELS.get(
                            export_format,
                            export_format.upper(),
                        ),
                        "icon": FORMAT_ICONS.get(
                            export_format,
                            "📦",
                        ),
                    }
                )

        cards.append(
            {
                "key": report_key,
                "title": report.title,
                "description": getattr(
                    report,
                    "description",
                    "",
                ),
                "supported_formats": (
                    supported_formats
                ),
                "preview_url": reverse(
                    "exports_center:preview",
                    kwargs={
                        "report_key": (
                            report_key
                        )
                    },
                ),
            }
        )

    return cards


def _build_filter_query(
    filters: dict[str, Any],
) -> str:
    """
    تحويل الفلاتر إلى Query String.
    """

    query_items: list[
        tuple[str, Any]
    ] = []

    for key, value in filters.items():
        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            for item in value:
                query_items.append(
                    (
                        key,
                        item,
                    )
                )

        else:
            query_items.append(
                (
                    key,
                    value,
                )
            )

    return urlencode(
        query_items,
        doseq=True,
    )


def _valid_export_statuses() -> set[str]:
    """
    إرجاع حالات التصدير المسموح بها.
    """

    return {
        value
        for value, _label
        in ExportLog.ExportStatus.choices
    }


def _valid_export_formats() -> set[str]:
    """
    إرجاع صيغ التصدير المسموح بها.
    """

    return {
        value
        for value, _label
        in ExportLog.ExportFormat.choices
    }


def _planned_file_name(report_key: str, export_format: str) -> str:
    extension = "xlsx" if export_format == FORMAT_EXCEL else export_format
    return f"{report_key}-{timezone.localtime():%Y%m%d-%H%M%S}.{extension}"


def _run_logged_export(
    request: HttpRequest,
    *,
    report,
    export_format: str,
    filters: dict[str, Any],
) -> HttpResponse:
    """Run every export through one auditable, recoverable workflow."""
    export_log = create_processing_log(
        request=request,
        module=report.module or report.key,
        report_key=report.key,
        file_name=_planned_file_name(report.key, export_format),
        export_format=export_format,
        filters=filters,
    )
    export_log.report_name = report.title
    export_log.started_at = timezone.now()
    export_log.save(update_fields=["report_name", "started_at", "updated_at"])

    try:
        result = export_report(
            report_key=report.key,
            export_format=export_format,
            filters=filters,
            user=request.user,
            allow_empty=True,
        )
        export_log.file_name = result.file_name
        complete_export_log(
            export_log=export_log,
            content=result.content,
            records_count=result.records_count,
        )
    except Exception as exc:
        fail_export_log(export_log=export_log, exception=exc)
        raise

    response = result.to_http_response()
    response["X-Export-Log-ID"] = str(export_log.pk)
    return response


# ==================================================
# لوحة مركز التصدير
# ==================================================

@login_required
@require_GET
def dashboard_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    الصفحة الرئيسية لمركز التصدير.
    """

    selected_report_key = (
        _normalize_report_key(
            request.GET.get(
                "report_key"
            )
        )
    )

    selected_report = (
        _get_report_or_404(
            selected_report_key
        )
    )

    completed_logs = ExportLog.objects.filter(
        status=ExportLog.ExportStatus.SUCCESS,
    )
    today = timezone.localdate()
    total_logs = ExportLog.objects.count()
    successful_count = completed_logs.count()
    last_export = completed_logs.order_by("-completed_at").first()

    context = {
        "page_title": "مركز التصدير",
        "report_cards": (
            _build_report_cards()
        ),
        "report_choices": (
            get_report_choices()
        ),
        "selected_report": (
            selected_report
        ),
        "selected_report_key": (
            selected_report_key
        ),
        "format_labels": FORMAT_LABELS,
        "total_reports": len(REPORT_REGISTRY),
        "exports_today": completed_logs.filter(created_at__date=today).count(),
        "active_export_users": completed_logs.exclude(user=None).values("user_id").distinct().count(),
        "export_success_rate": round((successful_count / total_logs) * 100) if total_logs else 100,
        "last_export_label": last_export.report_name if last_export else "لا توجد عمليات بعد",
    }

    return render(
        request,
        "exports_center/dashboard.html",
        context,
    )


# ==================================================
# صفحة الفلاتر
# ==================================================

@login_required
@require_GET
def filters_view(
    request: HttpRequest,
    report_key: str,
) -> HttpResponse:
    """
    صفحة تحديد فلاتر تقرير معين.
    """

    report = _get_report_or_404(
        report_key
    )

    filter_definitions = getattr(
        report,
        "filters",
        (),
    )

    supported_formats = []

    for export_format in (
        FORMAT_EXCEL,
        FORMAT_PDF,
        FORMAT_CSV,
    ):
        if report.supports_format(
            export_format
        ):
            supported_formats.append(
                {
                    "key": export_format,
                    "label": FORMAT_LABELS.get(
                        export_format,
                        export_format.upper(),
                    ),
                    "icon": FORMAT_ICONS.get(
                        export_format,
                        "📦",
                    ),
                }
            )

    context = {
        "page_title": (
            f"فلاتر {report.title}"
        ),
        "report": report,
        "report_key": report.key,
        "filter_definitions": (
            filter_definitions
        ),
        "supported_formats": (
            supported_formats
        ),
        "current_filters": (
            _extract_filters(request)
        ),
    }

    return render(
        request,
        "exports_center/filters.html",
        context,
    )


# ==================================================
# معاينة التقرير
# ==================================================

@login_required
@require_GET
def preview_view(
    request: HttpRequest,
    report_key: str,
) -> HttpResponse:
    """
    معاينة بيانات التقرير قبل التصدير.
    """

    report = _get_report_or_404(
        report_key
    )

    filters = _extract_filters(
        request
    )

    preview_limit = (
        _normalize_preview_limit(
            request.GET.get(
                "preview_limit",
                DEFAULT_PREVIEW_LIMIT,
            )
        )
    )

    try:
        preview_data = preview_report(
            report_key=report.key,
            filters=filters,
            limit=preview_limit,
        )

    except (
        ExportServiceError,
        ValidationError,
        ValueError,
        KeyError,
    ) as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            "exports_center:filters",
            report_key=report.key,
        )

    columns = report.get_columns(
        FORMAT_EXCEL
    )

    preview_rows: list[
        dict[str, Any]
    ] = []

    for row_number, record in enumerate(
        preview_data["records"],
        start=1,
    ):
        values = []

        for column in columns:
            try:
                value = column.get_value(
                    record
                )

            except Exception:
                value = ""

            values.append(
                {
                    "column": column,
                    "value": value,
                }
            )

        preview_rows.append(
            {
                "number": row_number,
                "record": record,
                "values": values,
            }
        )

    query_string = _build_filter_query(
        filters
    )

    export_urls = {}

    for export_format in (
        FORMAT_EXCEL,
        FORMAT_PDF,
        FORMAT_CSV,
    ):
        if not report.supports_format(
            export_format
        ):
            continue

        base_url = reverse(
            "exports_center:export",
            kwargs={
                "report_key": report.key,
                "export_format": (
                    export_format
                ),
            },
        )

        export_urls[
            export_format
        ] = (
            f"{base_url}?{query_string}"
            if query_string
            else base_url
        )

    context = {
        "page_title": (
            f"معاينة {report.title}"
        ),
        "report": report,
        "report_key": report.key,
        "columns": columns,
        "preview_rows": preview_rows,
        "records": (
            preview_data["records"]
        ),
        "records_count": (
            preview_data[
                "records_count"
            ]
        ),
        "preview_count": (
            preview_data[
                "preview_count"
            ]
        ),
        "indicators": (
            preview_data["indicators"]
        ),
        "filters": filters,
        "preview_limit": (
            preview_limit
        ),
        "export_urls": export_urls,
        "format_labels": FORMAT_LABELS,
        "query_string": query_string,
    }

    return render(
        request,
        "exports_center/preview.html",
        context,
    )


# ==================================================
# تنفيذ التصدير
# ==================================================

@login_required
@require_http_methods(
    [
        "GET",
        "POST",
    ]
)
def export_view(
    request: HttpRequest,
    report_key: str,
    export_format: str,
) -> HttpResponse:
    """
    إنشاء وتنزيل التقرير مباشرة.
    """

    report = _get_report_or_404(
        report_key
    )

    normalized_format = (
        _normalize_export_format(
            export_format
        )
    )

    filters = _extract_filters(
        request
    )

    try:
        return _run_logged_export(
            request,
            report=report,
            export_format=normalized_format,
            filters=filters,
        )

    except EmptyExportError as exc:
        messages.warning(
            request,
            str(exc),
        )

    except (
        UnsupportedExportFormatError,
        ReportFormatNotSupportedError,
    ) as exc:
        messages.error(
            request,
            str(exc),
        )

    except ExportServiceError as exc:
        messages.error(
            request,
            (
                "تعذر إنشاء ملف التقرير: "
                f"{exc}"
            ),
        )

    except Exception:
        messages.error(
            request,
            (
                "حدث خطأ غير متوقع أثناء "
                "إنشاء التقرير."
            ),
        )

    query_string = _build_filter_query(
        filters
    )

    preview_url = reverse(
        "exports_center:preview",
        kwargs={
            "report_key": report.key
        },
    )

    if query_string:
        preview_url = (
            f"{preview_url}?"
            f"{query_string}"
        )

    return redirect(
        preview_url
    )


# ==================================================
# التصدير من نموذج POST
# ==================================================

@login_required
@require_POST
def export_submit_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    استقبال نموذج تصدير موحد من لوحة المركز.
    """

    report_key = _normalize_report_key(
        request.POST.get(
            "report_key"
        )
    )

    export_format = (
        _normalize_export_format(
            request.POST.get(
                "export_format"
            )
        )
    )

    report = _get_report_or_404(
        report_key
    )

    filters = _extract_filters(
        request
    )

    try:
        return _run_logged_export(
            request,
            report=report,
            export_format=export_format,
            filters=filters,
        )

    except (
        ExportServiceError,
        ValidationError,
        ValueError,
    ) as exc:
        messages.error(
            request,
            str(exc),
        )

    query_string = _build_filter_query(
        filters
    )

    preview_url = reverse(
        "exports_center:preview",
        kwargs={
            "report_key": report.key
        },
    )

    if query_string:
        preview_url = (
            f"{preview_url}?"
            f"{query_string}"
        )

    return redirect(
        preview_url
    )


@login_required
@require_GET
def download_export_view(
    request: HttpRequest,
    export_log_id: int,
) -> HttpResponse:
    """Download the stored institutional copy of a completed export."""
    export_log = get_object_or_404(ExportLog, pk=export_log_id)
    if export_log.user_id != request.user.id and not request.user.is_staff:
        raise PermissionDenied("لا تملك صلاحية تنزيل هذا الملف.")
    if not export_log.is_ready_for_download:
        raise Http404("ملف التصدير غير متاح للتنزيل.")

    export_log.register_download()
    return FileResponse(
        export_log.file.open("rb"),
        as_attachment=True,
        filename=export_log.file_name,
    )


# ==================================================
# سجل عمليات التصدير
# ==================================================

@login_required
@require_GET
def logs_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    عرض سجل عمليات التصدير الحقيقي.

    يدعم الفلاتر التالية:
    - الحالة.
    - صيغة التصدير.
    - القسم.
    """

    status_filter = str(
        request.GET.get(
            "status"
        )
        or ""
    ).strip()

    format_filter = str(
        request.GET.get(
            "format"
        )
        or ""
    ).strip()

    module_filter = str(
        request.GET.get(
            "module"
        )
        or ""
    ).strip()

    logs = (
        ExportLog.objects
        .select_related(
            "user"
        )
        .all()
    )

    if status_filter in _valid_export_statuses():
        logs = logs.filter(
            status=status_filter
        )

    if format_filter in _valid_export_formats():
        logs = logs.filter(
            export_format=format_filter
        )

    if module_filter:
        logs = logs.filter(
            module=module_filter
        )

    logs = logs.order_by(
        "-created_at",
        "-id",
    )

    all_logs = ExportLog.objects.all()

    total_logs = all_logs.count()

    excel_count = all_logs.filter(
        export_format=(
            ExportLog
            .ExportFormat
            .EXCEL
        )
    ).count()

    pdf_count = all_logs.filter(
        export_format=(
            ExportLog
            .ExportFormat
            .PDF
        )
    ).count()

    csv_count = all_logs.filter(
        export_format=(
            ExportLog
            .ExportFormat
            .CSV
        )
    ).count()

    word_count = all_logs.filter(
        export_format=(
            ExportLog
            .ExportFormat
            .WORD
        )
    ).count()

    success_count = all_logs.filter(
        status=(
            ExportLog
            .ExportStatus
            .SUCCESS
        )
    ).count()

    failed_count = all_logs.filter(
        status=(
            ExportLog
            .ExportStatus
            .FAILED
        )
    ).count()

    processing_count = all_logs.filter(
        status=(
            ExportLog
            .ExportStatus
            .PROCESSING
        )
    ).count()

    pending_count = all_logs.filter(
        status=(
            ExportLog
            .ExportStatus
            .PENDING
        )
    ).count()

    module_choices = (
        all_logs
        .exclude(
            module=""
        )
        .values_list(
            "module",
            flat=True,
        )
        .distinct()
        .order_by(
            "module"
        )
    )

    context = {
        "page_title": "سجل عمليات التصدير",

        "logs": logs,

        "total_logs": total_logs,

        "excel_count": excel_count,
        "pdf_count": pdf_count,
        "csv_count": csv_count,
        "word_count": word_count,

        "success_count": success_count,
        "failed_count": failed_count,
        "processing_count": processing_count,
        "pending_count": pending_count,

        "selected_status": status_filter,
        "selected_format": format_filter,
        "selected_module": module_filter,

        "status_choices": (
            ExportLog
            .ExportStatus
            .choices
        ),

        "format_choices": (
            ExportLog
            .ExportFormat
            .choices
        ),

        "module_choices": module_choices,
    }

    return render(
        request,
        "exports_center/logs.html",
        context,
    )
