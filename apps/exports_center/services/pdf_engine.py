from __future__ import annotations

import base64
import html

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from apps.exports_center.registry import (
    FORMAT_PDF,
    ExportColumn,
    ExportReportDefinition,
    get_report_definition,
)
from apps.exports_center.selectors import (
    build_report_indicators,
    select_report_queryset,
)
from apps.exports_center.services.column_selector import (
    select_export_columns,
)


# ==================================================
# إعدادات PDF
# ==================================================

PDF_CONTENT_TYPE = "application/pdf"

AUTHORITY_NAME = (
    "الهيئة العامة للعناية بشؤون "
    "المسجد الحرام والمسجد النبوي"
)

PLATFORM_NAME = "منصة أبواب"

PLATFORM_SUBTITLE = (
    "نظام إدارة وتشغيل أبواب المسجد الحرام"
)


# ==================================================
# أخطاء محرك PDF
# ==================================================

class PDFExportError(Exception):
    """
    الخطأ الأساسي لمحرك PDF.
    """


class PDFLibraryNotInstalledError(
    PDFExportError
):
    """
    مكتبة إنشاء PDF غير مثبتة.
    """


class PDFGenerationError(
    PDFExportError
):
    """
    تعذر إنشاء ملف PDF.
    """


# ==================================================
# نتيجة إنشاء PDF
# ==================================================

@dataclass(frozen=True)
class PDFExportResult:
    """
    نتيجة إنشاء ملف PDF.
    """

    content: bytes
    file_name: str
    records_count: int
    indicators: dict[str, Any]
    report_key: str
    report_title: str

    @property
    def file_size(self) -> int:
        """
        حجم الملف بالبايت.
        """

        return len(
            self.content
        )


# ==================================================
# محرك PDF الموحد
# ==================================================

class PDFExportEngine:
    """
    محرك موحد لإنشاء تقارير PDF.

    الخصائص:
    - دعم كامل للغة العربية.
    - اتجاه من اليمين إلى اليسار.
    - رأس رسمي للهيئة ومنصة أبواب.
    - إدراج الشعارات عند توفرها.
    - عرض الفلاتر المستخدمة.
    - عرض مؤشرات التقرير.
    - جدول بيانات متعدد الصفحات.
    - تكرار رأس الجدول في كل صفحة.
    - ترقيم الصفحات.
    - دعم الوضع الأفقي والرأسي.
    - دعم أسماء الملفات العربية والإنجليزية.
    - اختيار أعمدة التقرير قبل التصدير.
    - الحفاظ على ترتيب الأعمدة المختارة.
    - رفض الأعمدة غير المصرح بها.
    """

    def __init__(
        self,
        *,
        authority_name: str = AUTHORITY_NAME,
        platform_name: str = PLATFORM_NAME,
        platform_subtitle: str = PLATFORM_SUBTITLE,
    ) -> None:
        self.authority_name = authority_name
        self.platform_name = platform_name
        self.platform_subtitle = platform_subtitle

    # ==================================================
    # الواجهة العامة
    # ==================================================

    def build(
        self,
        *,
        report_key: str,
        queryset=None,
        filters: Mapping[str, Any] | None = None,
        user=None,
        indicators: dict[str, Any] | None = None,
        file_name: str | None = None,
        selected_columns: (
            str
            | Iterable[str]
            | None
        ) = None,
    ) -> PDFExportResult:
        """
        إنشاء ملف PDF كامل.

        عند عدم تمرير queryset يتم جلب البيانات
        تلقائيًا من selectors.py.

        عند عدم تمرير selected_columns يتم استخدام
        جميع أعمدة التقرير المتاحة لصيغة PDF.
        """

        report = get_report_definition(
            report_key
        )

        if not report.supports_format(
            FORMAT_PDF
        ):
            raise ValueError(
                f"التقرير «{report.title}» "
                "لا يدعم صيغة PDF."
            )

        normalized_filters = (
            self._normalize_filters(
                filters
                or {}
            )
        )

        columns = select_export_columns(
            report=report,
            export_format=FORMAT_PDF,
            selected_columns=selected_columns,
            require_at_least_one=True,
            reject_unknown=True,
        )

        if queryset is None:
            queryset = select_report_queryset(
                report_key,
                normalized_filters,
            )

        records_count = queryset.count()

        if indicators is None:
            indicators = build_report_indicators(
                report_key,
                queryset,
            )

        html_content = self._build_html_document(
            report=report,
            queryset=queryset,
            columns=columns,
            filters=normalized_filters,
            user=user,
            indicators=indicators,
            records_count=records_count,
        )

        pdf_content = self._render_pdf(
            html_content
        )

        resolved_file_name = (
            file_name
            or self._build_file_name(
                report
            )
        )

        resolved_file_name = (
            self._ensure_pdf_extension(
                resolved_file_name
            )
        )

        return PDFExportResult(
            content=pdf_content,
            file_name=resolved_file_name,
            records_count=records_count,
            indicators=indicators,
            report_key=report.key,
            report_title=report.title,
        )

    def build_response(
        self,
        *,
        report_key: str,
        queryset=None,
        filters: Mapping[str, Any] | None = None,
        user=None,
        indicators: dict[str, Any] | None = None,
        file_name: str | None = None,
        selected_columns: (
            str
            | Iterable[str]
            | None
        ) = None,
    ) -> HttpResponse:
        """
        إنشاء استجابة تنزيل PDF مباشرة.
        """

        result = self.build(
            report_key=report_key,
            queryset=queryset,
            filters=filters,
            user=user,
            indicators=indicators,
            file_name=file_name,
            selected_columns=selected_columns,
        )

        response = HttpResponse(
            result.content,
            content_type=PDF_CONTENT_TYPE,
        )

        encoded_name = quote(
            result.file_name
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="{result.file_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        )

        response[
            "Content-Length"
        ] = str(
            result.file_size
        )

        response[
            "X-Content-Type-Options"
        ] = "nosniff"

        response[
            "Cache-Control"
        ] = (
            "private, no-store, "
            "max-age=0"
        )

        return response

    # ==================================================
    # إنشاء مستند HTML
    # ==================================================

    def _build_html_document(
        self,
        *,
        report: ExportReportDefinition,
        queryset,
        columns: tuple[ExportColumn, ...],
        filters: dict[str, Any],
        user,
        indicators: dict[str, Any],
        records_count: int,
    ) -> str:
        """
        إنشاء HTML كامل جاهز للتحويل إلى PDF.
        """

        page_orientation = (
            "landscape"
            if getattr(
                report,
                "landscape",
                False,
            )
            else "portrait"
        )

        logos_html = self._build_logos_html()

        metadata_html = self._build_metadata_html(
            user=user,
            filters=filters,
            records_count=records_count,
        )

        indicators_html = (
            self._build_indicators_html(
                indicators
            )
        )

        table_html = self._build_table_html(
            queryset=queryset,
            columns=columns,
            records_count=records_count,
        )

        font_css = self._build_font_css()

        report_title = html.escape(
            str(
                report.title
            )
        )

        authority_name = html.escape(
            self.authority_name
        )

        platform_name = html.escape(
            self.platform_name
        )

        platform_subtitle = html.escape(
            self.platform_subtitle
        )

        generated_at = (
            timezone.localtime()
            .strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        return f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">

    <style>
        {font_css}

        @page {{
            size: A4 {page_orientation};
            margin: 18mm 10mm 18mm 10mm;

            @bottom-right {{
                content: "{platform_name}";
                font-size: 8px;
                color: #66736e;
            }}

            @bottom-center {{
                content: "صفحة " counter(page)
                         " من " counter(pages);
                font-size: 8px;
                color: #66736e;
            }}

            @bottom-left {{
                content: "{generated_at}";
                font-size: 8px;
                color: #66736e;
            }}
        }}

        * {{
            box-sizing: border-box;
        }}

        html,
        body {{
            margin: 0;
            padding: 0;
            direction: rtl;
        }}

        body {{
            font-family:
                "AbwaabArabic",
                "Noto Sans Arabic",
                "DejaVu Sans",
                Arial,
                sans-serif;

            color: #17211e;
            font-size: 9px;
            line-height: 1.55;
            background: #ffffff;
        }}

        .report-container {{
            width: 100%;
        }}

        .official-header {{
            width: 100%;
            border-bottom: 3px solid #d4af37;
            padding-bottom: 8px;
            margin-bottom: 10px;
        }}

        .header-grid {{
            display: table;
            width: 100%;
            table-layout: fixed;
        }}

        .header-logo,
        .header-content {{
            display: table-cell;
            vertical-align: middle;
        }}

        .header-logo {{
            width: 18%;
            text-align: center;
        }}

        .header-content {{
            width: 64%;
            text-align: center;
        }}

        .header-logo img {{
            max-width: 95px;
            max-height: 62px;
            object-fit: contain;
        }}

        .logo-placeholder {{
            color: #0f7b5c;
            font-size: 11px;
            font-weight: 700;
        }}

        .authority-name {{
            margin: 0;
            color: #064e3b;
            font-size: 15px;
            font-weight: 700;
        }}

        .platform-name {{
            margin: 2px 0 0;
            color: #0f7b5c;
            font-size: 12px;
            font-weight: 700;
        }}

        .report-title {{
            margin: 5px 0 0;
            color: #17211e;
            font-size: 19px;
            font-weight: 800;
        }}

        .platform-subtitle {{
            margin: 2px 0 0;
            color: #66736e;
            font-size: 9px;
        }}

        .metadata-box {{
            margin: 8px 0 10px;
            padding: 7px 9px;
            border: 1px solid #e5d49a;
            background: #fff8e1;
            border-radius: 4px;
        }}

        .metadata-grid {{
            display: table;
            width: 100%;
            table-layout: fixed;
        }}

        .metadata-item {{
            display: table-cell;
            width: 25%;
            vertical-align: top;
            padding: 2px 5px;
        }}

        .metadata-label {{
            color: #66736e;
            font-size: 8px;
            font-weight: 700;
        }}

        .metadata-value {{
            color: #17211e;
            font-size: 9px;
            font-weight: 700;
            overflow-wrap: anywhere;
        }}

        .filters-box {{
            margin-top: 5px;
            padding-top: 5px;
            border-top: 1px solid #eadfb8;
        }}

        .filters-title {{
            color: #064e3b;
            font-weight: 700;
        }}

        .section-title {{
            margin: 10px 0 7px;
            padding: 6px 9px;
            color: #ffffff;
            background: #0f7b5c;
            border-right: 4px solid #d4af37;
            font-size: 11px;
            font-weight: 700;
        }}

        .indicators-grid {{
            display: table;
            width: 100%;
            table-layout: fixed;
            border-spacing: 5px;
            margin: -5px 0 7px;
        }}

        .indicator-card {{
            display: table-cell;
            vertical-align: middle;
            text-align: center;
            padding: 7px 5px;
            border: 1px solid #cfe7dd;
            background: #ecfdf5;
            border-radius: 4px;
        }}

        .indicator-label {{
            color: #66736e;
            font-size: 8px;
            font-weight: 700;
        }}

        .indicator-value {{
            margin-top: 2px;
            color: #064e3b;
            font-size: 13px;
            font-weight: 800;
        }}

        .indicators-list {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 8px;
        }}

        .indicators-list td {{
            border: 1px solid #dde6e2;
            padding: 5px 7px;
        }}

        .indicators-list .label {{
            width: 60%;
            color: #064e3b;
            background: #ecfdf5;
            font-weight: 700;
        }}

        .indicators-list .value {{
            width: 40%;
            text-align: center;
            font-weight: 700;
        }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            page-break-inside: auto;
        }}

        .data-table thead {{
            display: table-header-group;
        }}

        .data-table tfoot {{
            display: table-footer-group;
        }}

        .data-table tr {{
            page-break-inside: avoid;
            page-break-after: auto;
        }}

        .data-table th {{
            padding: 6px 4px;
            border: 1px solid #0a634b;
            color: #ffffff;
            background: #0f7b5c;
            text-align: center;
            vertical-align: middle;
            font-size: 8px;
            font-weight: 700;
            overflow-wrap: anywhere;
        }}

        .data-table td {{
            padding: 5px 4px;
            border: 1px solid #dde6e2;
            color: #17211e;
            text-align: center;
            vertical-align: middle;
            font-size: 7.5px;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}

        .data-table td.text-cell {{
            text-align: right;
        }}

        .data-table tbody tr:nth-child(even) {{
            background: #f7faf8;
        }}

        .data-table tbody tr:nth-child(odd) {{
            background: #ffffff;
        }}

        .row-number {{
            width: 30px;
            color: #064e3b;
            font-weight: 700;
        }}

        .empty-message {{
            padding: 20px;
            text-align: center;
            color: #66736e;
            background: #ecfdf5;
            border: 1px solid #cfe7dd;
            font-size: 11px;
            font-weight: 700;
        }}

        .records-summary {{
            margin-top: 8px;
            padding: 6px 9px;
            color: #064e3b;
            background: #ecfdf5;
            border: 1px solid #cfe7dd;
            text-align: center;
            font-weight: 700;
        }}

        .confidential-note {{
            margin-top: 8px;
            color: #66736e;
            text-align: center;
            font-size: 7px;
        }}
    </style>
</head>

<body>
    <main class="report-container">

        <header class="official-header">
            <div class="header-grid">
                {logos_html["right"]}

                <div class="header-content">
                    <h1 class="authority-name">
                        {authority_name}
                    </h1>

                    <div class="platform-name">
                        {platform_name}
                    </div>

                    <h2 class="report-title">
                        {report_title}
                    </h2>

                    <div class="platform-subtitle">
                        {platform_subtitle}
                    </div>
                </div>

                {logos_html["left"]}
            </div>
        </header>

        {metadata_html}

        {indicators_html}

        <section>
            <div class="section-title">
                بيانات التقرير
            </div>

            {table_html}
        </section>

        <div class="records-summary">
            إجمالي السجلات المصدرة:
            {records_count}
        </div>

        <div class="confidential-note">
            تم إنشاء هذا التقرير آليًا من منصة أبواب.
        </div>

    </main>
</body>
</html>
"""

    # ==================================================
    # رأس الشعارات
    # ==================================================

    def _build_logos_html(
        self,
    ) -> dict[str, str]:
        haramain_path = self._first_existing_path(
            self._haramain_logo_candidates()
        )

        abwaab_path = self._first_existing_path(
            self._abwaab_logo_candidates()
        )

        haramain_data = self._image_data_uri(
            haramain_path
        )

        abwaab_data = self._image_data_uri(
            abwaab_path
        )

        if haramain_data:
            right_logo = f"""
<div class="header-logo">
    <img
        src="{haramain_data}"
        alt="شعار الهيئة"
    >
</div>
"""
        else:
            right_logo = """
<div class="header-logo">
    <div class="logo-placeholder">
        الحرمين
    </div>
</div>
"""

        if abwaab_data:
            left_logo = f"""
<div class="header-logo">
    <img
        src="{abwaab_data}"
        alt="شعار منصة أبواب"
    >
</div>
"""
        else:
            left_logo = """
<div class="header-logo">
    <div class="logo-placeholder">
        منصة أبواب
    </div>
</div>
"""

        return {
            "right": right_logo,
            "left": left_logo,
        }

    # ==================================================
    # بيانات التقرير
    # ==================================================

    def _build_metadata_html(
        self,
        *,
        user,
        filters: dict[str, Any],
        records_count: int,
    ) -> str:
        exported_by = html.escape(
            self._display_user(
                user
            )
            or "—"
        )

        exported_at = (
            timezone.localtime()
            .strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        filters_html = self._build_filters_html(
            filters
        )

        return f"""
<section class="metadata-box">
    <div class="metadata-grid">

        <div class="metadata-item">
            <div class="metadata-label">
                المستخدم
            </div>

            <div class="metadata-value">
                {exported_by}
            </div>
        </div>

        <div class="metadata-item">
            <div class="metadata-label">
                تاريخ التصدير
            </div>

            <div class="metadata-value">
                {exported_at}
            </div>
        </div>

        <div class="metadata-item">
            <div class="metadata-label">
                عدد السجلات
            </div>

            <div class="metadata-value">
                {records_count}
            </div>
        </div>

        <div class="metadata-item">
            <div class="metadata-label">
                صيغة التقرير
            </div>

            <div class="metadata-value">
                PDF
            </div>
        </div>

    </div>

    {filters_html}
</section>
"""

    # ==================================================
    # الفلاتر
    # ==================================================

    def _build_filters_html(
        self,
        filters: dict[str, Any],
    ) -> str:
        formatted_filters = self._format_filters(
            filters
        )

        if not formatted_filters:
            return """
<div class="filters-box">
    <span class="filters-title">
        الفلاتر:
    </span>
    جميع السجلات
</div>
"""

        items_html = " | ".join(
            (
                f"<strong>{html.escape(label)}:</strong> "
                f"{html.escape(value)}"
            )
            for label, value
            in formatted_filters
        )

        return f"""
<div class="filters-box">
    <span class="filters-title">
        الفلاتر:
    </span>

    {items_html}
</div>
"""

    def _format_filters(
        self,
        filters: dict[str, Any],
    ) -> list[tuple[str, str]]:
        ignored_keys = {
            "csrfmiddlewaretoken",
            "page",
            "page_size",
            "preview",
            "preview_limit",
            "export_format",
            "format",
            "report_key",
            "submit",
            "selected_columns",
            "columns",
            "search",
            "sort",
            "direction",
            "ordering",
            "action",
        }

        formatted_filters: list[
            tuple[str, str]
        ] = []

        for key, value in filters.items():
            if key in ignored_keys:
                continue

            if value in (
                None,
                "",
                [],
                (),
                {},
            ):
                continue

            formatted_filters.append(
                (
                    self._filter_label(
                        key
                    ),
                    self._display_filter_value(
                        value
                    ),
                )
            )

        return formatted_filters

    @staticmethod
    def _filter_label(
        key: str,
    ) -> str:
        labels = {
            "date_from": "من تاريخ",
            "date_to": "إلى تاريخ",
            "shift_plan": "الوردية",
            "shift_plan_id": "الوردية",
            "zone": "المنطقة",
            "zone_id": "المنطقة",
            "door_direction": "جهة الأبواب",
            "door_state": "حالة الباب",
            "incident_status": "حالة البلاغ",
            "maintenance_status": "حالة الصيانة",
            "report_status": "حالة التقرير",
            "employee": "الموظف",
            "employee_id": "الموظف",
            "technician": "الفني",
            "technician_id": "الفني",
            "priority": "الأولوية",
            "job_title": "المسمى الوظيفي",
            "work_status": "حالة الموظف",
            "is_active": "حالة التفعيل",
            "is_confirmed": "حالة التأكيد",
            "report_type": "نوع التقرير",
            "role": "الدور",
            "shift_type": "نوع الوردية",
            "shift_type_id": "نوع الوردية",
            "rest_days": "أيام الراحة",
            "incident_type": "نوع البلاغ",
            "q": "البحث",
            "search": "البحث",
        }

        return labels.get(
            key,
            key.replace(
                "_",
                " ",
            ),
        )

    # ==================================================
    # المؤشرات
    # ==================================================

    def _build_indicators_html(
        self,
        indicators: dict[str, Any],
    ) -> str:
        flattened = self._flatten_indicators(
            indicators
        )

        if not flattened:
            return ""

        primary_indicators = flattened[:4]
        remaining_indicators = flattened[4:]

        cards_html = "".join(
            f"""
<div class="indicator-card">
    <div class="indicator-label">
        {html.escape(label)}
    </div>

    <div class="indicator-value">
        {html.escape(self._display_value(value))}
    </div>
</div>
"""
            for label, value
            in primary_indicators
        )

        remaining_html = ""

        if remaining_indicators:
            rows_html = "".join(
                f"""
<tr>
    <td class="label">
        {html.escape(label)}
    </td>

    <td class="value">
        {html.escape(self._display_value(value))}
    </td>
</tr>
"""
                for label, value
                in remaining_indicators
            )

            remaining_html = f"""
<table class="indicators-list">
    <tbody>
        {rows_html}
    </tbody>
</table>
"""

        return f"""
<section>
    <div class="section-title">
        مؤشرات التقرير
    </div>

    <div class="indicators-grid">
        {cards_html}
    </div>

    {remaining_html}
</section>
"""

    def _flatten_indicators(
        self,
        indicators: dict[str, Any],
    ) -> list[tuple[str, Any]]:
        labels = {
            "records_count": "عدد السجلات",
            "active_count": "السجلات النشطة",
            "inactive_count": "السجلات غير النشطة",
            "confirmed_count": "التسكينات المؤكدة",
            "unconfirmed_count": "التسكينات غير المؤكدة",
            "employees_count": "عدد الموظفين",
            "doors_count": "عدد الأبواب",
            "shifts_count": "عدد الورديات",
            "active_doors": "الأبواب النشطة",
            "inactive_doors": "الأبواب غير النشطة",
            "zones_count": "عدد المناطق",
            "total_doors": "إجمالي الأبواب",
            "open_doors": "الأبواب المفتوحة",
            "maintenance_requests": "طلبات الصيانة",
            "generated_at": "وقت إنشاء المؤشرات",
            "status_totals": "حسب الحالة",
            "priority_totals": "حسب الأولوية",
        }

        flattened: list[
            tuple[str, Any]
        ] = []

        for key, value in indicators.items():
            label = labels.get(
                key,
                key.replace(
                    "_",
                    " ",
                ),
            )

            if isinstance(
                value,
                list,
            ):
                for item in value:
                    if isinstance(
                        item,
                        dict,
                    ):
                        item_name = (
                            item.get(
                                "status"
                            )
                            or item.get(
                                "priority"
                            )
                            or item.get(
                                "label"
                            )
                            or "غير محدد"
                        )

                        item_total = (
                            item.get(
                                "total"
                            )
                            or item.get(
                                "count"
                            )
                            or 0
                        )

                        flattened.append(
                            (
                                f"{label} - "
                                f"{item_name}",
                                item_total,
                            )
                        )

                    else:
                        flattened.append(
                            (
                                label,
                                item,
                            )
                        )

            elif isinstance(
                value,
                dict,
            ):
                for (
                    child_key,
                    child_value,
                ) in value.items():
                    flattened.append(
                        (
                            f"{label} - "
                            f"{child_key}",
                            child_value,
                        )
                    )

            else:
                flattened.append(
                    (
                        label,
                        value,
                    )
                )

        return flattened

    # ==================================================
    # جدول البيانات
    # ==================================================

    def _build_table_html(
        self,
        *,
        queryset,
        columns: tuple[ExportColumn, ...],
        records_count: int,
    ) -> str:
        if records_count == 0:
            return """
<div class="empty-message">
    لا توجد بيانات مطابقة للفلاتر المحددة.
</div>
"""

        headers_html = """
<th class="row-number">
    م
</th>
"""

        headers_html += "".join(
            f"""
<th>
    {html.escape(str(column.header))}
</th>
"""
            for column in columns
        )

        rows: list[str] = []

        for row_number, record in enumerate(
            queryset.iterator(
                chunk_size=500
            ),
            start=1,
        ):
            cells_html = [
                f"""
<td class="row-number">
    {row_number}
</td>
"""
            ]

            for column in columns:
                try:
                    raw_value = column.get_value(
                        record
                    )

                except Exception:
                    raw_value = ""

                display_value = (
                    self._display_value(
                        raw_value
                    )
                )

                css_class = (
                    "text-cell"
                    if getattr(
                        column,
                        "wrap_text",
                        False,
                    )
                    else ""
                )

                cells_html.append(
                    f"""
<td class="{css_class}">
    {html.escape(display_value)}
</td>
"""
                )

            rows.append(
                f"""
<tr>
    {''.join(cells_html)}
</tr>
"""
            )

        return f"""
<table class="data-table">
    <thead>
        <tr>
            {headers_html}
        </tr>
    </thead>

    <tbody>
        {''.join(rows)}
    </tbody>
</table>
"""

    # ==================================================
    # تحويل HTML إلى PDF
    # ==================================================

    def _render_pdf(
        self,
        html_content: str,
    ) -> bytes:
        """
        تحويل HTML إلى PDF باستخدام WeasyPrint.
        """

        try:
            from weasyprint import HTML

        except ImportError as exc:
            raise PDFLibraryNotInstalledError(
                "مكتبة WeasyPrint غير مثبتة. "
                "نفذ الأمر: pip install weasyprint"
            ) from exc

        try:
            pdf_content = HTML(
                string=html_content,
                base_url=str(
                    settings.BASE_DIR
                ),
            ).write_pdf()

        except Exception as exc:
            raise PDFGenerationError(
                "تعذر إنشاء ملف PDF. "
                f"تفاصيل الخطأ: {exc}"
            ) from exc

        if not pdf_content:
            raise PDFGenerationError(
                "تم إنشاء ملف PDF فارغ."
            )

        return pdf_content

    # ==================================================
    # تنسيق القيم
    # ==================================================

    def _display_value(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return "—"

        if isinstance(
            value,
            bool,
        ):
            return (
                "نعم"
                if value
                else "لا"
            )

        if isinstance(
            value,
            datetime,
        ):
            if timezone.is_aware(
                value
            ):
                value = timezone.localtime(
                    value
                )

            return value.strftime(
                "%Y-%m-%d %H:%M"
            )

        if isinstance(
            value,
            date,
        ):
            return value.strftime(
                "%Y-%m-%d"
            )

        if isinstance(
            value,
            Decimal,
        ):
            return format(
                value,
                "f",
            )

        if isinstance(
            value,
            dict,
        ):
            return " | ".join(
                (
                    f"{key}: "
                    f"{self._display_value(item)}"
                )
                for key, item
                in value.items()
            )

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return "، ".join(
                self._display_value(
                    item
                )
                for item in value
            )

        return (
            str(
                value
            )
            .replace(
                "\x00",
                "",
            )
            .strip()
            or "—"
        )

    @staticmethod
    def _display_filter_value(
        value: Any,
    ) -> str:
        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return "، ".join(
                str(
                    item
                )
                for item in value
            )

        if isinstance(
            value,
            bool,
        ):
            return (
                "نعم"
                if value
                else "لا"
            )

        return str(
            value
        )

    @staticmethod
    def _display_user(
        user,
    ) -> str:
        if not user:
            return ""

        get_full_name = getattr(
            user,
            "get_full_name",
            None,
        )

        if callable(
            get_full_name
        ):
            full_name = (
                get_full_name()
                or ""
            ).strip()

            if full_name:
                return full_name

        employee = getattr(
            user,
            "employee",
            None,
        )

        if employee:
            full_name = getattr(
                employee,
                "full_name",
                "",
            )

            if full_name:
                return str(
                    full_name
                )

        return str(
            getattr(
                user,
                "username",
                "",
            )
            or ""
        )

    # ==================================================
    # الخطوط
    # ==================================================

    def _build_font_css(
        self,
    ) -> str:
        font_path = self._first_existing_path(
            self._font_candidates()
        )

        if not font_path:
            return ""

        font_data = self._file_data_uri(
            font_path,
            mime_type="font/ttf",
        )

        if not font_data:
            return ""

        return f"""
@font-face {{
    font-family: "AbwaabArabic";
    src: url("{font_data}");
    font-weight: normal;
    font-style: normal;
}}
"""

    def _font_candidates(
        self,
    ) -> tuple[Path, ...]:
        base_dir = Path(
            settings.BASE_DIR
        )

        return (
            base_dir
            / "static"
            / "fonts"
            / "NotoKufiArabic-Regular.ttf",

            base_dir
            / "static"
            / "fonts"
            / "NotoSansArabic-Regular.ttf",

            base_dir
            / "static"
            / "fonts"
            / "Cairo-Regular.ttf",

            base_dir
            / "static"
            / "fonts"
            / "Tajawal-Regular.ttf",

            base_dir
            / "static"
            / "fonts"
            / "Amiri-Regular.ttf",
        )

    # ==================================================
    # مسارات الشعارات
    # ==================================================

    def _haramain_logo_candidates(
        self,
    ) -> tuple[Path, ...]:
        base_dir = Path(
            settings.BASE_DIR
        )

        media_root = Path(
            settings.MEDIA_ROOT
        )

        return (
            media_root
            / "aharamain_logo.png",

            media_root
            / "aharamaian_logo.png",

            media_root
            / "alharamain_logo.png",

            media_root
            / "haramain_logo.png",

            media_root
            / "شعار الحرمين.png",

            base_dir
            / "static"
            / "images"
            / "aharamain_logo.png",

            base_dir
            / "static"
            / "images"
            / "haramain_logo.png",

            base_dir
            / "static"
            / "img"
            / "aharamain_logo.png",

            base_dir
            / "static"
            / "img"
            / "haramain_logo.png",

            base_dir
            / "static"
            / "img"
            / "شعار الحرمين.png",
        )

    def _abwaab_logo_candidates(
        self,
    ) -> tuple[Path, ...]:
        base_dir = Path(
            settings.BASE_DIR
        )

        media_root = Path(
            settings.MEDIA_ROOT
        )

        return (
            media_root
            / "abwaab-logo.jpeg",

            media_root
            / "abwaab-logo.jpg",

            media_root
            / "abwaab-logo.png",

            media_root
            / "abwaab_logo.png",

            base_dir
            / "static"
            / "images"
            / "abwaab-logo.jpeg",

            base_dir
            / "static"
            / "images"
            / "abwaab-logo.jpg",

            base_dir
            / "static"
            / "images"
            / "abwaab-logo.png",

            base_dir
            / "static"
            / "images"
            / "abwaab_logo.png",

            base_dir
            / "static"
            / "img"
            / "abwaab-logo.jpeg",

            base_dir
            / "static"
            / "img"
            / "abwaab-logo.png",
        )

    # ==================================================
    # تحويل الملفات إلى Data URI
    # ==================================================

    @staticmethod
    def _first_existing_path(
        paths: Iterable[Path],
    ) -> Path | None:
        for path in paths:
            if (
                path.exists()
                and path.is_file()
            ):
                return path

        return None

    def _image_data_uri(
        self,
        path: Path | None,
    ) -> str:
        if not path:
            return ""

        suffix = path.suffix.lower()

        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }

        mime_type = mime_types.get(
            suffix
        )

        if not mime_type:
            return ""

        return self._file_data_uri(
            path,
            mime_type=mime_type,
        )

    @staticmethod
    def _file_data_uri(
        path: Path,
        *,
        mime_type: str,
    ) -> str:
        try:
            encoded = base64.b64encode(
                path.read_bytes()
            ).decode(
                "ascii"
            )

        except (
            OSError,
            ValueError,
        ):
            return ""

        return (
            f"data:{mime_type};base64,"
            f"{encoded}"
        )

    # ==================================================
    # تنظيف الفلاتر
    # ==================================================

    @staticmethod
    def _normalize_filters(
        filters: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized: dict[
            str,
            Any
        ] = {}

        lists_method = getattr(
            filters,
            "lists",
            None,
        )

        if callable(
            lists_method
        ):
            for key, values in lists_method():
                cleaned_values = [
                    (
                        value.strip()
                        if isinstance(
                            value,
                            str,
                        )
                        else value
                    )
                    for value in values
                    if value not in (
                        None,
                        "",
                    )
                ]

                if not cleaned_values:
                    continue

                normalized[key] = (
                    cleaned_values[0]
                    if len(
                        cleaned_values
                    ) == 1
                    else cleaned_values
                )

            return normalized

        for key, value in filters.items():
            if isinstance(
                value,
                str,
            ):
                value = value.strip()

            if value in (
                None,
                "",
                [],
                (),
                {},
            ):
                continue

            normalized[key] = value

        return normalized

    # ==================================================
    # اسم الملف
    # ==================================================

    @staticmethod
    def _build_file_name(
        report: ExportReportDefinition,
    ) -> str:
        timestamp = (
            timezone.localtime()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        return (
            f"{report.filename_prefix}_"
            f"{timestamp}.pdf"
        )

    @staticmethod
    def _ensure_pdf_extension(
        file_name: str,
    ) -> str:
        normalized_name = (
            str(
                file_name
                or "export"
            )
            .replace(
                '"',
                "",
            )
            .replace(
                "\r",
                "",
            )
            .replace(
                "\n",
                "",
            )
            .strip()
        )

        if not normalized_name:
            normalized_name = "export"

        if not normalized_name.lower().endswith(
            ".pdf"
        ):
            normalized_name += ".pdf"

        return normalized_name


# ==================================================
# نسخة افتراضية جاهزة
# ==================================================

pdf_export_engine = PDFExportEngine()


# ==================================================
# دوال مختصرة
# ==================================================

def build_pdf_export(
    *,
    report_key: str,
    queryset=None,
    filters: Mapping[str, Any] | None = None,
    user=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
    selected_columns: (
        str
        | Iterable[str]
        | None
    ) = None,
) -> PDFExportResult:
    """
    إنشاء ملف PDF باستخدام المحرك الافتراضي.
    """

    return pdf_export_engine.build(
        report_key=report_key,
        queryset=queryset,
        filters=filters,
        user=user,
        indicators=indicators,
        file_name=file_name,
        selected_columns=selected_columns,
    )


def build_pdf_response(
    *,
    report_key: str,
    queryset=None,
    filters: Mapping[str, Any] | None = None,
    user=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
    selected_columns: (
        str
        | Iterable[str]
        | None
    ) = None,
) -> HttpResponse:
    """
    إنشاء استجابة تنزيل PDF مباشرة.
    """

    return pdf_export_engine.build_response(
        report_key=report_key,
        queryset=queryset,
        filters=filters,
        user=user,
        indicators=indicators,
        file_name=file_name,
        selected_columns=selected_columns,
    )