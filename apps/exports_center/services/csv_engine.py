from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import Any, Mapping
from urllib.parse import quote

from django.http import HttpResponse
from django.utils import timezone

from apps.exports_center.registry import (
    FORMAT_CSV,
    ExportColumn,
    ExportReportDefinition,
    get_report_definition,
)
from apps.exports_center.selectors import (
    build_report_indicators,
    select_report_queryset,
)


# ==================================================
# ترميز CSV
# ==================================================

CSV_ENCODING = "utf-8-sig"

CSV_CONTENT_TYPE = (
    "text/csv; charset=utf-8"
)


# ==================================================
# نتيجة إنشاء CSV
# ==================================================

@dataclass(frozen=True)
class CSVExportResult:
    """
    نتيجة بناء ملف CSV.
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
        return len(self.content)


# ==================================================
# محرك CSV الموحد
# ==================================================

class CSVExportEngine:
    """
    محرك موحد لإنشاء ملفات CSV.

    الخصائص:
    - ترميز UTF-8 مع BOM لدعم العربية في Excel.
    - استخدام أعمدة التقرير المسجلة في registry.py.
    - تطبيق نفس selectors المستخدمة في Excel.
    - دعم الفلاتر.
    - دعم أسماء الملفات الآمنة.
    - دعم القيم المعقدة.
    - منع حقن صيغ Excel داخل CSV.
    """

    def __init__(
        self,
        *,
        encoding: str = CSV_ENCODING,
        delimiter: str = ",",
        quotechar: str = '"',
        lineterminator: str = "\r\n",
    ) -> None:
        self.encoding = encoding
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.lineterminator = lineterminator

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
    ) -> CSVExportResult:
        """
        إنشاء ملف CSV كامل.
        """
        report = get_report_definition(
            report_key
        )

        if not report.supports_format(
            FORMAT_CSV
        ):
            raise ValueError(
                f"التقرير {report.title} "
                "لا يدعم صيغة CSV."
            )

        normalized_filters = (
            self._normalize_filters(
                filters or {}
            )
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

        content = self._build_content(
            report=report,
            queryset=queryset,
        )

        resolved_file_name = (
            file_name
            or self._build_file_name(
                report
            )
        )

        return CSVExportResult(
            content=content,
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
    ) -> HttpResponse:
        """
        إنشاء استجابة تنزيل CSV مباشرة.
        """
        result = self.build(
            report_key=report_key,
            queryset=queryset,
            filters=filters,
            user=user,
            indicators=indicators,
            file_name=file_name,
        )

        response = HttpResponse(
            result.content,
            content_type=CSV_CONTENT_TYPE,
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

        return response

    # ==================================================
    # بناء المحتوى
    # ==================================================

    def _build_content(
        self,
        *,
        report: ExportReportDefinition,
        queryset,
    ) -> bytes:
        columns = report.get_columns(
            FORMAT_CSV
        )

        stream = StringIO(
            newline=""
        )

        writer = csv.writer(
            stream,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator=self.lineterminator,
        )

        self._write_headers(
            writer=writer,
            columns=columns,
        )

        for record in queryset.iterator(
            chunk_size=1000
        ):
            self._write_record(
                writer=writer,
                record=record,
                columns=columns,
            )

        text_content = stream.getvalue()

        stream.close()

        return text_content.encode(
            self.encoding
        )

    # ==================================================
    # رؤوس الأعمدة
    # ==================================================

    @staticmethod
    def _write_headers(
        *,
        writer,
        columns: tuple[ExportColumn, ...],
    ) -> None:
        writer.writerow(
            [
                column.header
                for column in columns
            ]
        )

    # ==================================================
    # كتابة سجل
    # ==================================================

    def _write_record(
        self,
        *,
        writer,
        record,
        columns: tuple[ExportColumn, ...],
    ) -> None:
        row_values: list[Any] = []

        for column in columns:
            try:
                raw_value = column.get_value(
                    record
                )

            except Exception:
                raw_value = ""

            safe_value = self._safe_csv_value(
                raw_value
            )

            row_values.append(
                safe_value
            )

        writer.writerow(
            row_values
        )

    # ==================================================
    # القيم الآمنة
    # ==================================================

    def _safe_csv_value(
        self,
        value: Any,
    ) -> str:
        """
        تحويل القيم إلى نص آمن.

        يمنع CSV Injection عند فتح الملف في Excel.
        """
        if value is None:
            return ""

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
                "%Y-%m-%d %H:%M:%S"
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
            bool,
        ):
            return (
                "نعم"
                if value
                else "لا"
            )

        if isinstance(
            value,
            dict,
        ):
            value = " | ".join(
                f"{key}: {item}"
                for key, item
                in value.items()
            )

        elif isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            value = "، ".join(
                str(item)
                for item in value
            )

        else:
            value = str(value)

        value = self._normalize_text(
            value
        )

        return self._prevent_formula_injection(
            value
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """
        تنظيف النص من المحارف غير المناسبة.
        """
        return (
            str(value)
            .replace("\x00", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

    @staticmethod
    def _prevent_formula_injection(
        value: str,
    ) -> str:
        """
        منع تفسير النص كصيغة Excel.

        Excel قد يفسر القيم التي تبدأ بـ:
        =
        +
        -
        @
        كصيغ قابلة للتنفيذ.
        """
        if not value:
            return ""

        dangerous_prefixes = (
            "=",
            "+",
            "-",
            "@",
            "\t",
        )

        if value.startswith(
            dangerous_prefixes
        ):
            return f"'{value}"

        return value

    # ==================================================
    # تنظيف الفلاتر
    # ==================================================

    @staticmethod
    def _normalize_filters(
        filters: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        for key, value in filters.items():
            if isinstance(
                value,
                str,
            ):
                normalized[key] = (
                    value.strip()
                )
            else:
                normalized[key] = value

        return normalized

    # ==================================================
    # اسم الملف
    # ==================================================

    @staticmethod
    def _build_file_name(
        report: ExportReportDefinition,
    ) -> str:
        timestamp = timezone.localtime().strftime(
            "%Y%m%d_%H%M%S"
        )

        return (
            f"{report.filename_prefix}_"
            f"{timestamp}.csv"
        )


# ==================================================
# نسخة افتراضية
# ==================================================

csv_export_engine = CSVExportEngine()


# ==================================================
# دوال مختصرة
# ==================================================

def build_csv_export(
    *,
    report_key: str,
    queryset=None,
    filters: Mapping[str, Any] | None = None,
    user=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
) -> CSVExportResult:
    """
    إنشاء ملف CSV باستخدام المحرك الافتراضي.
    """
    return csv_export_engine.build(
        report_key=report_key,
        queryset=queryset,
        filters=filters,
        user=user,
        indicators=indicators,
        file_name=file_name,
    )


def build_csv_response(
    *,
    report_key: str,
    queryset=None,
    filters: Mapping[str, Any] | None = None,
    user=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
) -> HttpResponse:
    """
    إنشاء استجابة تنزيل CSV مباشرة.
    """
    return csv_export_engine.build_response(
        report_key=report_key,
        queryset=queryset,
        filters=filters,
        user=user,
        indicators=indicators,
        file_name=file_name,
    )