from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from django.http import HttpResponse
from django.utils import timezone

from apps.exports_center.registry import (
    FORMAT_EXCEL,
    get_report_definition,
)
from apps.exports_center.selectors import (
    build_report_indicators,
    select_report_queryset,
)
from apps.exports_center.services.csv_engine import (
    CSV_CONTENT_TYPE,
    CSVExportResult,
    build_csv_export,
)
from apps.exports_center.services.excel_engine import (
    ExcelExportResult,
    build_excel_export,
)
from apps.exports_center.services.pdf_engine import (
    PDF_CONTENT_TYPE,
    PDFExportResult,
    build_pdf_export,
)


# ==================================================
# ثوابت صيغ التصدير
# ==================================================

EXPORT_FORMAT_EXCEL = FORMAT_EXCEL
EXPORT_FORMAT_PDF = "pdf"
EXPORT_FORMAT_CSV = "csv"

SUPPORTED_EXPORT_FORMATS = (
    EXPORT_FORMAT_EXCEL,
    EXPORT_FORMAT_PDF,
    EXPORT_FORMAT_CSV,
)


# ==================================================
# أنواع الأخطاء
# ==================================================

class ExportServiceError(Exception):
    """
    الخطأ الأساسي لخدمة التصدير.
    """


class UnsupportedExportFormatError(
    ExportServiceError
):
    """
    الصيغة المطلوبة غير مدعومة.
    """


class ReportFormatNotSupportedError(
    ExportServiceError
):
    """
    التقرير لا يدعم الصيغة المطلوبة.
    """


class ExportEngineNotReadyError(
    ExportServiceError
):
    """
    محرك الصيغة غير جاهز.
    """


class EmptyExportError(
    ExportServiceError
):
    """
    لا توجد بيانات قابلة للتصدير.
    """


# ==================================================
# نتيجة التصدير الموحدة
# ==================================================

@dataclass(frozen=True)
class ExportServiceResult:
    """
    نتيجة موحدة لجميع عمليات التصدير.

    تستخدم مع:
    - Excel
    - PDF
    - CSV
    - سجل عمليات التصدير
    - استجابات التنزيل
    """

    content: bytes
    file_name: str
    content_type: str
    report_key: str
    report_title: str
    export_format: str
    records_count: int
    indicators: dict[str, Any]
    generated_at: Any

    @property
    def file_size(self) -> int:
        """
        حجم الملف بالبايت.
        """
        return len(self.content)

    @property
    def is_empty(self) -> bool:
        """
        هل التقرير بلا سجلات؟
        """
        return self.records_count == 0

    def to_http_response(
        self,
    ) -> HttpResponse:
        """
        تحويل نتيجة التصدير إلى استجابة تنزيل.
        """
        response = HttpResponse(
            self.content,
            content_type=self.content_type,
        )

        response[
            "Content-Disposition"
        ] = _build_content_disposition(
            self.file_name
        )

        response[
            "Content-Length"
        ] = str(
            self.file_size
        )

        response[
            "X-Export-Report"
        ] = self.report_key

        response[
            "X-Export-Format"
        ] = self.export_format

        response[
            "X-Export-Records"
        ] = str(
            self.records_count
        )

        return response


# ==================================================
# خدمة التصدير المركزية
# ==================================================

class ExportService:
    """
    الخدمة المركزية لإنشاء ملفات التقارير.

    دورة العمل:
    1. التحقق من التقرير.
    2. التحقق من صيغة التصدير.
    3. تنظيف الفلاتر.
    4. جلب QuerySet.
    5. حساب المؤشرات.
    6. تشغيل محرك التصدير.
    7. توحيد النتيجة.
    8. إرجاع الملف أو HttpResponse.
    """

    def export(
        self,
        *,
        report_key: str,
        export_format: str,
        filters: Mapping[str, Any] | None = None,
        user=None,
        queryset=None,
        indicators: dict[str, Any] | None = None,
        file_name: str | None = None,
        allow_empty: bool = True,
    ) -> ExportServiceResult:
        """
        تنفيذ عملية تصدير وإرجاع نتيجة موحدة.
        """
        normalized_report_key = (
            self._normalize_report_key(
                report_key
            )
        )

        normalized_format = (
            self._normalize_export_format(
                export_format
            )
        )

        report = get_report_definition(
            normalized_report_key
        )

        self._validate_format(
            report=report,
            export_format=normalized_format,
        )

        normalized_filters = (
            self.normalize_filters(
                filters or {}
            )
        )

        if queryset is None:
            queryset = select_report_queryset(
                normalized_report_key,
                normalized_filters,
            )

        records_count = queryset.count()

        if (
            records_count == 0
            and not allow_empty
        ):
            raise EmptyExportError(
                "لا توجد بيانات مطابقة "
                "للفلاتر المحددة."
            )

        if indicators is None:
            indicators = build_report_indicators(
                normalized_report_key,
                queryset,
            )

        if normalized_format == EXPORT_FORMAT_EXCEL:
            return self._export_excel(
                report_key=normalized_report_key,
                queryset=queryset,
                filters=normalized_filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )

        if normalized_format == EXPORT_FORMAT_PDF:
            return self._export_pdf(
                report_key=normalized_report_key,
                queryset=queryset,
                filters=normalized_filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )

        if normalized_format == EXPORT_FORMAT_CSV:
            return self._export_csv(
                report_key=normalized_report_key,
                queryset=queryset,
                filters=normalized_filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )

        raise UnsupportedExportFormatError(
            f"صيغة التصدير غير مدعومة: "
            f"{normalized_format}"
        )

    def export_response(
        self,
        *,
        report_key: str,
        export_format: str,
        filters: Mapping[str, Any] | None = None,
        user=None,
        queryset=None,
        indicators: dict[str, Any] | None = None,
        file_name: str | None = None,
        allow_empty: bool = True,
    ) -> HttpResponse:
        """
        تنفيذ التصدير وإرجاع استجابة تنزيل مباشرة.
        """
        result = self.export(
            report_key=report_key,
            export_format=export_format,
            filters=filters,
            user=user,
            queryset=queryset,
            indicators=indicators,
            file_name=file_name,
            allow_empty=allow_empty,
        )

        return result.to_http_response()

    def preview(
        self,
        *,
        report_key: str,
        filters: Mapping[str, Any] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        تجهيز بيانات المعاينة دون إنشاء ملف.
        """
        normalized_report_key = (
            self._normalize_report_key(
                report_key
            )
        )

        report = get_report_definition(
            normalized_report_key
        )

        normalized_filters = (
            self.normalize_filters(
                filters or {}
            )
        )

        queryset = select_report_queryset(
            normalized_report_key,
            normalized_filters,
        )

        records_count = queryset.count()

        safe_limit = self._normalize_preview_limit(
            limit
        )

        records = list(
            queryset[:safe_limit]
        )

        indicators = build_report_indicators(
            normalized_report_key,
            queryset,
        )

        return {
            "report": report,
            "report_key": report.key,
            "report_title": report.title,
            "filters": normalized_filters,
            "queryset": queryset,
            "records": records,
            "records_count": records_count,
            "preview_count": len(records),
            "indicators": indicators,
            "generated_at": timezone.localtime(),
        }

    # ==================================================
    # محرك Excel
    # ==================================================

    def _export_excel(
        self,
        *,
        report_key: str,
        queryset,
        filters: Mapping[str, Any],
        user,
        indicators: dict[str, Any],
        file_name: str | None,
    ) -> ExportServiceResult:
        """
        إنشاء ملف Excel وإرجاع نتيجة موحدة.
        """
        excel_result: ExcelExportResult = (
            build_excel_export(
                report_key=report_key,
                queryset=queryset,
                filters=filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )
        )

        return ExportServiceResult(
            content=excel_result.content,
            file_name=excel_result.file_name,
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            report_key=excel_result.report_key,
            report_title=excel_result.report_title,
            export_format=EXPORT_FORMAT_EXCEL,
            records_count=excel_result.records_count,
            indicators=excel_result.indicators,
            generated_at=timezone.localtime(),
        )

    # ==================================================
    # محرك PDF
    # ==================================================

    def _export_pdf(
        self,
        *,
        report_key: str,
        queryset,
        filters: Mapping[str, Any],
        user,
        indicators: dict[str, Any],
        file_name: str | None,
    ) -> ExportServiceResult:
        """
        إنشاء ملف PDF وإرجاع نتيجة موحدة.
        """
        pdf_result: PDFExportResult = (
            build_pdf_export(
                report_key=report_key,
                queryset=queryset,
                filters=filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )
        )

        return ExportServiceResult(
            content=pdf_result.content,
            file_name=pdf_result.file_name,
            content_type=PDF_CONTENT_TYPE,
            report_key=pdf_result.report_key,
            report_title=pdf_result.report_title,
            export_format=EXPORT_FORMAT_PDF,
            records_count=pdf_result.records_count,
            indicators=pdf_result.indicators,
            generated_at=timezone.localtime(),
        )

    # ==================================================
    # محرك CSV
    # ==================================================

    def _export_csv(
        self,
        *,
        report_key: str,
        queryset,
        filters: Mapping[str, Any],
        user,
        indicators: dict[str, Any],
        file_name: str | None,
    ) -> ExportServiceResult:
        """
        إنشاء ملف CSV وإرجاع نتيجة موحدة.
        """
        csv_result: CSVExportResult = (
            build_csv_export(
                report_key=report_key,
                queryset=queryset,
                filters=filters,
                user=user,
                indicators=indicators,
                file_name=file_name,
            )
        )

        return ExportServiceResult(
            content=csv_result.content,
            file_name=csv_result.file_name,
            content_type=CSV_CONTENT_TYPE,
            report_key=csv_result.report_key,
            report_title=csv_result.report_title,
            export_format=EXPORT_FORMAT_CSV,
            records_count=csv_result.records_count,
            indicators=csv_result.indicators,
            generated_at=timezone.localtime(),
        )

    # ==================================================
    # التحقق من الصيغ
    # ==================================================

    def _validate_format(
        self,
        *,
        report,
        export_format: str,
    ) -> None:
        """
        التحقق من أن الصيغة مدعومة عمومًا
        ومدعومة داخل تعريف التقرير.
        """
        if export_format not in SUPPORTED_EXPORT_FORMATS:
            raise UnsupportedExportFormatError(
                f"صيغة التصدير غير مدعومة: "
                f"{export_format}"
            )

        supports_format = getattr(
            report,
            "supports_format",
            None,
        )

        if (
            callable(supports_format)
            and not supports_format(
                export_format
            )
        ):
            raise ReportFormatNotSupportedError(
                f"التقرير «{report.title}» "
                f"لا يدعم صيغة "
                f"{export_format.upper()}."
            )

    # ==================================================
    # تنظيف الفلاتر
    # ==================================================

    def normalize_filters(
        self,
        filters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        تحويل الفلاتر إلى قاموس قابل لإعادة الاستخدام.

        يدعم:
        - dict
        - QueryDict
        - cleaned_data
        """
        normalized: dict[str, Any] = {}

        if not filters:
            return normalized

        lists_method = getattr(
            filters,
            "lists",
            None,
        )

        if callable(lists_method):
            for key, values in lists_method():
                cleaned_values = [
                    self._normalize_filter_value(
                        value
                    )
                    for value in values
                    if value not in (
                        None,
                        "",
                    )
                ]

                if not cleaned_values:
                    continue

                if len(cleaned_values) == 1:
                    normalized[key] = (
                        cleaned_values[0]
                    )
                else:
                    normalized[key] = (
                        cleaned_values
                    )

            return normalized

        for key, value in filters.items():
            normalized_value = (
                self._normalize_filter_value(
                    value
                )
            )

            if normalized_value in (
                None,
                "",
                [],
                (),
                {},
            ):
                continue

            normalized[key] = (
                normalized_value
            )

        return normalized

    @staticmethod
    def _normalize_filter_value(
        value: Any,
    ) -> Any:
        """
        تنظيف قيمة فلتر واحدة.
        """
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, tuple):
            return list(value)

        return value

    # ==================================================
    # تطبيع المدخلات
    # ==================================================

    @staticmethod
    def _normalize_report_key(
        report_key: str,
    ) -> str:
        """
        تطبيع مفتاح التقرير.
        """
        normalized_key = (
            str(report_key or "")
            .strip()
            .lower()
        )

        if not normalized_key:
            raise ExportServiceError(
                "يجب تحديد مفتاح التقرير."
            )

        return normalized_key

    @staticmethod
    def _normalize_export_format(
        export_format: str,
    ) -> str:
        """
        تطبيع صيغة التصدير ودعم الأسماء البديلة.
        """
        normalized_format = (
            str(export_format or "")
            .strip()
            .lower()
        )

        format_aliases = {
            "xlsx": EXPORT_FORMAT_EXCEL,
            "xls": EXPORT_FORMAT_EXCEL,
            "excel": EXPORT_FORMAT_EXCEL,
            "pdf": EXPORT_FORMAT_PDF,
            "csv": EXPORT_FORMAT_CSV,
        }

        resolved_format = format_aliases.get(
            normalized_format,
            normalized_format,
        )

        if not resolved_format:
            raise ExportServiceError(
                "يجب تحديد صيغة التصدير."
            )

        return resolved_format

    @staticmethod
    def _normalize_preview_limit(
        limit: Any,
    ) -> int:
        """
        ضبط عدد سجلات المعاينة بين 1 و200.
        """
        try:
            normalized_limit = int(limit)

        except (
            TypeError,
            ValueError,
        ):
            normalized_limit = 50

        return max(
            1,
            min(
                normalized_limit,
                200,
            ),
        )


# ==================================================
# نسخة الخدمة الافتراضية
# ==================================================

export_service = ExportService()


# ==================================================
# دوال مختصرة
# ==================================================

def export_report(
    *,
    report_key: str,
    export_format: str,
    filters: Mapping[str, Any] | None = None,
    user=None,
    queryset=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
    allow_empty: bool = True,
) -> ExportServiceResult:
    """
    إنشاء ملف تقرير وإرجاع النتيجة الموحدة.
    """
    return export_service.export(
        report_key=report_key,
        export_format=export_format,
        filters=filters,
        user=user,
        queryset=queryset,
        indicators=indicators,
        file_name=file_name,
        allow_empty=allow_empty,
    )


def export_report_response(
    *,
    report_key: str,
    export_format: str,
    filters: Mapping[str, Any] | None = None,
    user=None,
    queryset=None,
    indicators: dict[str, Any] | None = None,
    file_name: str | None = None,
    allow_empty: bool = True,
) -> HttpResponse:
    """
    إنشاء التقرير وإرجاع استجابة تنزيل مباشرة.
    """
    return export_service.export_response(
        report_key=report_key,
        export_format=export_format,
        filters=filters,
        user=user,
        queryset=queryset,
        indicators=indicators,
        file_name=file_name,
        allow_empty=allow_empty,
    )


def preview_report(
    *,
    report_key: str,
    filters: Mapping[str, Any] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    تجهيز معاينة التقرير.
    """
    return export_service.preview(
        report_key=report_key,
        filters=filters,
        limit=limit,
    )


# ==================================================
# ترويسة تنزيل الملف
# ==================================================

def _build_content_disposition(
    file_name: str,
) -> str:
    """
    إنشاء Content-Disposition متوافق مع
    أسماء الملفات العربية والإنجليزية.
    """
    safe_file_name = (
        str(file_name or "export")
        .replace('"', "")
        .replace("\r", "")
        .replace("\n", "")
    )

    encoded_file_name = quote(
        safe_file_name
    )

    return (
        f'attachment; filename="{safe_file_name}"; '
        f"filename*=UTF-8''{encoded_file_name}"
    )