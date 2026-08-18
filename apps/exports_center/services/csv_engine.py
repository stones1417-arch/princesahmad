from __future__ import annotations

import csv

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any, Iterable, Mapping
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
from apps.exports_center.services.column_selector import (
    select_export_columns,
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

        return len(
            self.content
        )


# ==================================================
# محرك CSV الموحد
# ==================================================

class CSVExportEngine:
    """
    محرك موحد لإنشاء ملفات CSV.

    الخصائص:
    - ترميز UTF-8 مع BOM لدعم العربية في Excel.
    - استخدام أعمدة التقرير المسجلة في registry.py.
    - تطبيق نفس selectors المستخدمة في Excel وPDF.
    - دعم الفلاتر.
    - دعم اختيار الأعمدة قبل التصدير.
    - الحفاظ على ترتيب الأعمدة الذي اختاره المستخدم.
    - رفض الأعمدة غير الموجودة أو غير المصرح بها.
    - دعم أسماء الملفات الآمنة.
    - دعم القيم المعقدة.
    - منع حقن صيغ Excel داخل CSV.
    - معالجة الملفات الكبيرة باستخدام iterator.
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
        selected_columns: (
            str
            | Iterable[str]
            | None
        ) = None,
    ) -> CSVExportResult:
        """
        إنشاء ملف CSV كامل.

        عند عدم تمرير queryset يتم جلب البيانات
        تلقائيًا من selectors.py.

        عند عدم تمرير selected_columns يتم استخدام
        جميع أعمدة التقرير المتاحة لصيغة CSV.
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
                filters
                or {}
            )
        )

        columns = select_export_columns(
            report=report,
            export_format=FORMAT_CSV,
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

        content = self._build_content(
            queryset=queryset,
            columns=columns,
        )

        resolved_file_name = (
            file_name
            or self._build_file_name(
                report
            )
        )

        resolved_file_name = (
            self._ensure_csv_extension(
                resolved_file_name
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
        selected_columns: (
            str
            | Iterable[str]
            | None
        ) = None,
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
            selected_columns=selected_columns,
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
    # بناء المحتوى
    # ==================================================

    def _build_content(
        self,
        *,
        queryset,
        columns: tuple[ExportColumn, ...],
    ) -> bytes:
        """
        بناء محتوى CSV باستخدام الأعمدة المختارة فقط.
        """

        stream = StringIO(
            newline=""
        )

        try:
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

            text_content = (
                stream.getvalue()
            )

        finally:
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
        """
        كتابة رؤوس الأعمدة المختارة.
        """

        writer.writerow(
            [
                str(
                    getattr(
                        column,
                        "header",
                        "",
                    )
                    or ""
                )
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
        """
        كتابة صف واحد داخل ملف CSV.
        """

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
            value = " | ".join(
                (
                    f"{key}: "
                    f"{self._safe_nested_value(item)}"
                )
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
                self._safe_nested_value(
                    item
                )
                for item in value
            )

        else:
            value = str(
                value
            )

        value = self._normalize_text(
            value
        )

        return self._prevent_formula_injection(
            value
        )

    def _safe_nested_value(
        self,
        value: Any,
    ) -> str:
        """
        تحويل القيم المتداخلة إلى نص نظيف.
        """

        if value is None:
            return ""

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
            Decimal,
        ):
            return format(
                value,
                "f",
            )

        return self._normalize_text(
            str(
                value
            )
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """
        تنظيف النص من المحارف غير المناسبة.
        """

        return (
            str(
                value
            )
            .replace(
                "\x00",
                "",
            )
            .replace(
                "\r\n",
                "\n",
            )
            .replace(
                "\r",
                "\n",
            )
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
        أو Tab
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
        """
        تنظيف الفلاتر قبل تمريرها إلى selectors.
        """

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
        """
        إنشاء اسم افتراضي لملف CSV.
        """

        timestamp = (
            timezone.localtime()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        return (
            f"{report.filename_prefix}_"
            f"{timestamp}.csv"
        )

    @staticmethod
    def _ensure_csv_extension(
        file_name: str,
    ) -> str:
        """
        تنظيف اسم الملف وضمان امتداد CSV.
        """

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
            ".csv"
        ):
            normalized_name += ".csv"

        return normalized_name


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
    selected_columns: (
        str
        | Iterable[str]
        | None
    ) = None,
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
        selected_columns=selected_columns,
    )


def build_csv_response(
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
    إنشاء استجابة تنزيل CSV مباشرة.
    """

    return csv_export_engine.build_response(
        report_key=report_key,
        queryset=queryset,
        filters=filters,
        user=user,
        indicators=indicators,
        file_name=file_name,
        selected_columns=selected_columns,
    )