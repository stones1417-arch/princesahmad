from __future__ import annotations

import json
import logging
import math
import time

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
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
from apps.hr.models import Employee
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_access import has_institutional_scope
from apps.exports_center.services.export_logger import (
    complete_export_log,
    create_processing_log,
    fail_export_log,
)
from apps.exports_center.tasks import build_export_file_task
from apps.exports_center.services.export_service import (
    EmptyExportError,
    ExportServiceError,
    ReportFormatNotSupportedError,
    UnsupportedExportFormatError,
    export_service,
    export_report,
    preview_report,
)
from apps.exports_center.services.column_selector import (
    build_available_columns,
    extract_selected_columns,
    select_export_columns,
)

from .forms import (
    FilterForm,
    InstitutionalContactForm,
)


logger = logging.getLogger("platform.exports")


def _require_export_permission(request: HttpRequest) -> None:
    if request.user.is_superuser:
        return
    if (
        not user_has_permission(request.user, PlatformPermissions.EXPORT_REPORT)
        or not has_institutional_scope(request.user)
    ):
        raise PermissionDenied("لا تملك صلاحية التصدير المؤسسي.")


# ==========================================================
# الثوابت
# ==========================================================

DEFAULT_REPORT_KEY = "employees"

DEFAULT_PREVIEW_LIMIT = 50
MAX_PREVIEW_LIMIT = 200

DEFAULT_PAGE_SIZE = 50
ALLOWED_PAGE_SIZES = {
    25,
    50,
    100,
}

MAX_AJAX_PREVIEW_RECORDS = 1000

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

AJAX_CONTROL_KEYS = {
    "search",
    "sort",
    "direction",
    "page",
    "page_size",
    "preview_limit",
    "ordering",
}


# ==========================================================
# أدوات مساعدة عامة
# ==========================================================

def _get_report_or_404(
    report_key: str,
):
    """
    جلب تعريف التقرير أو إرجاع خطأ 404.
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


def _normalize_positive_integer(
    value: Any,
    *,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """
    تحويل قيمة إلى عدد صحيح موجب ضمن حدود آمنة.
    """

    try:
        normalized = int(value)

    except (
        TypeError,
        ValueError,
    ):
        normalized = default

    normalized = max(
        minimum,
        normalized,
    )

    if maximum is not None:
        normalized = min(
            normalized,
            maximum,
        )

    return normalized


def _normalize_preview_limit(
    value: Any,
) -> int:
    """
    ضبط عدد سجلات المعاينة التقليدية.
    """

    return _normalize_positive_integer(
        value,
        default=DEFAULT_PREVIEW_LIMIT,
        minimum=1,
        maximum=MAX_PREVIEW_LIMIT,
    )


def _normalize_page(
    value: Any,
) -> int:
    """
    ضبط رقم الصفحة.
    """

    return _normalize_positive_integer(
        value,
        default=1,
        minimum=1,
    )


def _normalize_page_size(
    value: Any,
) -> int:
    """
    ضبط عدد السجلات المعروضة في الصفحة.
    """

    try:
        page_size = int(value)

    except (
        TypeError,
        ValueError,
    ):
        page_size = DEFAULT_PAGE_SIZE

    if page_size not in ALLOWED_PAGE_SIZES:
        return DEFAULT_PAGE_SIZE

    return page_size


def _normalize_sort_direction(
    value: Any,
) -> str:
    """
    السماح باتجاهي الترتيب فقط.
    """

    normalized = str(
        value
        or "asc"
    ).strip().lower()

    if normalized == "desc":
        return "desc"

    return "asc"


def _normalize_search_term(
    value: Any,
) -> str:
    """
    تنظيف عبارة البحث ومنع الأحجام المبالغ فيها.
    """

    return strip_tags(
        str(
            value
            or ""
        )
    ).strip()[:200]


def _extract_filters(
    request: HttpRequest,
) -> dict[str, Any]:
    """
    استخراج فلاتر التقرير من GET أو POST.

    يتم حذف حقول التحكم الخاصة بالواجهة
    حتى لا تصل إلى محددات بيانات التقرير.
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
        "page_size",
        "search",
        "sort",
        "direction",
        "ordering",
        "selected_columns",
        "columns",
    }

    filters: dict[str, Any] = {}

    for key in source.keys():
        if key in ignored_keys:
            continue

        values = [
            (
                value.strip()
                if isinstance(
                    value,
                    str,
                )
                else value
            )
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


def _create_report_filter_form_class(
    report_key: str,
) -> type[FilterForm]:
    """
    إنشاء فئة نموذج فلاتر ديناميكية حسب نوع التقرير.
    """

    extra_fields: dict[str, forms.Field] = {}

    report = REPORT_REGISTRY.get(
        report_key
    )

    report_filters = tuple(
        getattr(
            report,
            "filters",
            (),
        )
    )

    def _report_filter_choices(
        parameter: str,
        default_choices: tuple[
            tuple[str, str],
            ...,
        ],
    ) -> tuple[
        tuple[str, str],
        ...,
    ]:
        for report_filter in report_filters:
            if str(
                getattr(
                    report_filter,
                    "parameter",
                    "",
                )
                or ""
            ).strip() != parameter:
                continue

            choices = tuple(
                getattr(
                    report_filter,
                    "choices",
                    (),
                )
            )

            if not choices:
                return default_choices

            normalized_choices = tuple(
                (
                    ""
                    if str(choice_key) == "all"
                    else str(choice_key),
                    str(choice_label),
                )
                for choice_key, choice_label in choices
            )

            return normalized_choices

        return default_choices

    section_report_keys = {
        "shift_assignments",
        "door_distribution",
        "incidents",
        "maintenance",
        "reports",
    }

    if report_key in section_report_keys:
        extra_fields["section"] = forms.ChoiceField(
            required=False,
            label="القسم التشغيلي",
            choices=_report_filter_choices(
                "section",
                (
                    ("", "الكل"),
                    ("male", "رجالي"),
                    ("female", "نسائي"),
                ),
            ),
            widget=forms.Select,
        )

    if report_key == "locations":
        extra_fields["operational_section"] = forms.ChoiceField(
            required=False,
            label="القسم التشغيلي",
            choices=_report_filter_choices(
                "operational_section",
                (
                    ("", "الكل"),
                    ("male", "رجالي"),
                    ("female", "نسائي"),
                    ("shared", "مشترك"),
                ),
            ),
            widget=forms.Select,
        )

    if report_key == "employees":
        extra_fields["operational_section"] = forms.ChoiceField(
            required=False,
            label="القسم التشغيلي",
            choices=_report_filter_choices(
                "operational_section",
                (
                    ("", "الكل"),
                    *Employee.OperationalSection.choices,
                ),
            ),
            widget=forms.Select,
        )

        extra_fields["job_title"] = forms.ChoiceField(
            required=False,
            label="المسمى الوظيفي",
            choices=(
                ("", "جميع المسميات"),
                *Employee.JobTitle.choices,
            ),
            widget=forms.Select,
        )

        extra_fields["work_status"] = forms.ChoiceField(
            required=False,
            label="الحالة الوظيفية",
            choices=(
                ("", "كل الحالات"),
                *Employee.WorkStatus.choices,
            ),
            widget=forms.Select,
        )

        extra_fields["is_active"] = forms.ChoiceField(
            required=False,
            label="حالة التفعيل",
            choices=(
                ("", "الكل"),
                ("true", "نشط"),
                ("false", "غير نشط"),
            ),
            widget=forms.Select,
        )

    return type(
        f"{report_key.capitalize()}FilterForm",
        (FilterForm,),
        extra_fields,
    )


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
            if not report.supports_format(
                export_format
            ):
                continue

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
                        "report_key": report_key,
                    },
                ),
            }
        )

    return cards


def _build_filter_query(
    filters: dict[str, Any],
    *,
    selected_columns: list[str] | None = None,
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

    for column_key in selected_columns or []:
        query_items.append(
            (
                "selected_columns",
                column_key,
            )
        )

    return urlencode(
        query_items,
        doseq=True,
    )


def _build_applied_filters_for_preview(
    report,
    filters: dict[str, Any],
) -> list[dict[str, str]]:
    """
    تجهيز الفلاتر المعروضة في صفحة المعاينة بعناوين عربية.
    """
    if not filters:
        return []

    definitions = getattr(
        report,
        "filters",
        (),
    )

    label_by_parameter: dict[str, str] = {}
    choices_by_parameter: dict[str, dict[str, str]] = {}

    for definition in definitions:
        parameter = str(
            getattr(
                definition,
                "parameter",
                "",
            )
            or ""
        ).strip()

        if not parameter:
            continue

        label_by_parameter[parameter] = str(
            getattr(
                definition,
                "label",
                parameter,
            )
        )

        choices_map: dict[str, str] = {}
        for choice_value, choice_label in getattr(
            definition,
            "choices",
            (),
        ):
            choices_map[str(choice_value)] = str(
                choice_label
            )

        if choices_map:
            choices_by_parameter[
                parameter
            ] = choices_map

    applied_filters: list[dict[str, str]] = []

    for key, raw_value in filters.items():
        normalized_key = str(key).strip()
        value_text = str(
            raw_value
            if raw_value is not None
            else ""
        ).strip()

        if value_text in {
            "",
            "all",
        }:
            continue

        display_label = label_by_parameter.get(
            normalized_key,
            normalized_key,
        )

        display_value = value_text

        choices_map = choices_by_parameter.get(
            normalized_key,
            {},
        )

        if choices_map:
            display_value = choices_map.get(
                value_text,
                display_value,
            )

        applied_filters.append(
            {
                "key": normalized_key,
                "label": display_label,
                "value": display_value,
            }
        )

    return applied_filters


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


def _planned_file_name(
    report_key: str,
    export_format: str,
) -> str:
    """
    إنشاء اسم مبدئي لملف التصدير.
    """

    extension = (
        "xlsx"
        if export_format == FORMAT_EXCEL
        else export_format
    )

    return (
        f"{report_key}-"
        f"{timezone.localtime():%Y%m%d-%H%M%S}."
        f"{extension}"
    )


# ==========================================================
# أدوات تجهيز المعاينة
# ==========================================================

def _serialize_preview_value(
    value: Any,
) -> Any:
    """
    تحويل قيم المعاينة إلى قيم آمنة للقالب وJSON.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        if timezone.is_aware(value):
            value = timezone.localtime(
                value
            )

        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return str(value)

    if isinstance(
        value,
        UUID,
    ):
        return str(value)

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        (
            int,
            float,
            str,
        ),
    ):
        return value

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _serialize_preview_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _serialize_preview_value(
                item
            )
            for item in value
        ]

    return str(value)


def _detect_value_type(
    value: Any,
) -> str:
    """
    تحديد نوع القيمة لأغراض العرض والترتيب.
    """

    if value is None:
        return "empty"

    if isinstance(
        value,
        bool,
    ):
        return "boolean"

    if isinstance(
        value,
        (
            int,
            float,
            Decimal,
        ),
    ):
        return "number"

    if isinstance(
        value,
        datetime,
    ):
        return "datetime"

    if isinstance(
        value,
        date,
    ):
        return "date"

    return "text"


def _get_column_key(
    column: Any,
    index: int,
) -> str:
    """
    إرجاع مفتاح ثابت وآمن للعمود.
    """

    possible_keys = (
        getattr(
            column,
            "key",
            None,
        ),
        getattr(
            column,
            "source",
            None,
        ),
        f"column_{index}",
    )

    for key in possible_keys:
        normalized = str(
            key
            or ""
        ).strip()

        if normalized:
            return normalized

    return f"column_{index}"


def _get_column_header(
    column: Any,
    index: int,
) -> str:
    """
    إرجاع عنوان العمود دون طباعة كائن ExportColumn.
    """

    possible_headers = (
        getattr(
            column,
            "header",
            None,
        ),
        getattr(
            column,
            "label",
            None,
        ),
        getattr(
            column,
            "title",
            None,
        ),
        getattr(
            column,
            "key",
            None,
        ),
        f"العمود {index}",
    )

    for header in possible_headers:
        normalized = str(
            header
            or ""
        ).strip()

        if normalized:
            return normalized

    return f"العمود {index}"


def _get_column_declared_type(
    column: Any,
) -> str:
    """
    قراءة نوع العمود المعرّف إن كان موجودًا.
    """

    for attribute_name in (
        "data_type",
        "value_type",
        "column_type",
        "type",
    ):
        value = getattr(
            column,
            attribute_name,
            None,
        )

        if value:
            return str(
                value
            ).strip().lower()

    return "text"


def _build_preview_columns(
    export_columns: list[Any] | tuple[Any, ...],
) -> list[dict[str, Any]]:
    """
    تجهيز بيانات الأعمدة للقالب وواجهة Ajax.
    """

    columns: list[dict[str, Any]] = []

    for index, export_column in enumerate(
        export_columns,
        start=1,
    ):
        columns.append(
            {
                "key": _get_column_key(
                    export_column,
                    index,
                ),
                "header": _get_column_header(
                    export_column,
                    index,
                ),
                "type": _get_column_declared_type(
                    export_column
                ),
                "sortable": True,
                "export_column": export_column,
            }
        )

    return columns


def _build_record_url(
    record: Any,
) -> str:
    """
    محاولة الحصول على رابط السجل الأصلي إن كان متاحًا.

    لا يتم تكوين رابط افتراضي من معرف السجل منعًا
    لكشف مسارات غير مصرح بها.
    """

    get_absolute_url = getattr(
        record,
        "get_absolute_url",
        None,
    )

    if not callable(
        get_absolute_url
    ):
        return ""

    try:
        return str(
            get_absolute_url()
            or ""
        )

    except Exception:
        logger.exception(
            "Failed to build record URL for preview record."
        )

        return ""


def _build_preview_rows(
    *,
    records: list[Any],
    columns: list[dict[str, Any]],
    start_number: int = 1,
) -> list[dict[str, Any]]:
    """
    تجهيز صفوف المعاينة.
    """

    rows: list[dict[str, Any]] = []

    for row_offset, record in enumerate(
        records,
    ):
        values: list[dict[str, Any]] = []

        searchable_parts: list[str] = []

        for column_data in columns:
            export_column = column_data[
                "export_column"
            ]

            try:
                raw_value = export_column.get_value(
                    record
                )

            except Exception:
                logger.exception(
                    "Failed to resolve preview column %s.",
                    column_data["key"],
                )

                raw_value = None

            value_type = _detect_value_type(
                raw_value
            )

            serialized_value = (
                _serialize_preview_value(
                    raw_value
                )
            )

            display_value = (
                ""
                if serialized_value is None
                else str(
                    serialized_value
                )
            )

            searchable_parts.append(
                display_value.casefold()
            )

            values.append(
                {
                    "key": column_data["key"],
                    "header": column_data["header"],
                    "value": serialized_value,
                    "display_value": display_value,
                    "type": value_type,
                }
            )

        record_id = getattr(
            record,
            "pk",
            None,
        )

        rows.append(
            {
                "number": (
                    start_number
                    + row_offset
                ),
                "record_id": (
                    str(record_id)
                    if record_id is not None
                    else ""
                ),
                "record_url": _build_record_url(
                    record
                ),
                "values": values,
                "search_text": " ".join(
                    searchable_parts
                ),
            }
        )

    return rows


def _remove_private_column_data(
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    حذف كائن ExportColumn قبل إرسال البيانات للقالب أو JSON.
    """

    return [
        {
            key: value
            for key, value in column.items()
            if key != "export_column"
        }
        for column in columns
    ]


def _search_preview_rows(
    rows: list[dict[str, Any]],
    search_term: str,
) -> list[dict[str, Any]]:
    """
    البحث النصي داخل جميع خلايا المعاينة.
    """

    if not search_term:
        return rows

    normalized_search = (
        search_term.casefold()
    )

    return [
        row
        for row in rows
        if normalized_search
        in row.get(
            "search_text",
            "",
        )
    ]


def _get_row_sort_value(
    row: dict[str, Any],
    sort_key: str,
) -> tuple[int, Any]:
    """
    استخراج قيمة قابلة للترتيب من صف معين.
    """

    for item in row.get(
        "values",
        [],
    ):
        if item.get(
            "key"
        ) != sort_key:
            continue

        value = item.get(
            "value"
        )

        value_type = item.get(
            "type",
            "text",
        )

        if value in (
            None,
            "",
        ):
            return (
                1,
                "",
            )

        if value_type == "number":
            try:
                return (
                    0,
                    float(value),
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        return (
            0,
            str(
                value
            ).casefold(),
        )

    return (
        1,
        "",
    )


def _sort_preview_rows(
    rows: list[dict[str, Any]],
    *,
    sort_key: str,
    direction: str,
    allowed_keys: set[str],
) -> list[dict[str, Any]]:
    """
    ترتيب الصفوف حسب عمود مسموح فقط.
    """

    if (
        not sort_key
        or sort_key not in allowed_keys
    ):
        return rows

    reverse = (
        direction == "desc"
    )

    return sorted(
        rows,
        key=lambda row: _get_row_sort_value(
            row,
            sort_key,
        ),
        reverse=reverse,
    )


def _paginate_preview_rows(
    rows: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    """
    تقسيم صفوف المعاينة إلى صفحات.
    """

    total_records = len(
        rows
    )

    total_pages = max(
        1,
        math.ceil(
            total_records
            / page_size
        ),
    )

    current_page = min(
        page,
        total_pages,
    )

    start_index = (
        current_page - 1
    ) * page_size

    end_index = (
        start_index
        + page_size
    )

    paginated_rows = rows[
        start_index:end_index
    ]

    for row_number, row in enumerate(
        paginated_rows,
        start=(
            start_index
            + 1
        ),
    ):
        row["number"] = row_number

    pagination = {
        "page": current_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_records": total_records,
        "has_previous": (
            current_page > 1
        ),
        "has_next": (
            current_page
            < total_pages
        ),
        "previous_page": (
            current_page - 1
            if current_page > 1
            else None
        ),
        "next_page": (
            current_page + 1
            if current_page < total_pages
            else None
        ),
        "start_record": (
            start_index + 1
            if total_records
            else 0
        ),
        "end_record": min(
            end_index,
            total_records,
        ),
    }

    return (
        paginated_rows,
        pagination,
    )


def _estimate_preview_size(
    payload: Any,
) -> dict[str, Any]:
    """
    تقدير حجم بيانات المعاينة المرسلة.
    """

    try:
        raw_size = len(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ).encode(
                "utf-8"
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        raw_size = 0

    if raw_size < 1024:
        label = f"{raw_size} بايت"

    elif raw_size < (
        1024 * 1024
    ):
        label = (
            f"{raw_size / 1024:.1f} كيلوبايت"
        )

    else:
        label = (
            f"{raw_size / (1024 * 1024):.2f} ميجابايت"
        )

    return {
        "bytes": raw_size,
        "label": label,
    }


def _build_export_urls(
    *,
    report: Any,
    filters: dict[str, Any],
    selected_columns: list[str] | None = None,
) -> dict[str, str]:
    """
    إنشاء روابط التصدير المتاحة.
    """

    query_string = _build_filter_query(
        filters,
        selected_columns=selected_columns,
    )

    export_urls: dict[str, str] = {}

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

    return export_urls


def _run_logged_export(
    request: HttpRequest,
    *,
    report: Any,
    export_format: str,
    filters: dict[str, Any],
    selected_columns: list[str] | None = None,
) -> HttpResponse:
    """
    تنفيذ عملية تصدير مسجلة وقابلة للتدقيق.
    """

    normalized_filters = (
        export_service.normalize_filters(
            filters
        )
    )

    export_log = create_processing_log(
        request=request,
        module=(
            report.module
            or report.key
        ),
        report_key=report.key,
        file_name=_planned_file_name(
            report.key,
            export_format,
        ),
        export_format=export_format,
        filters=normalized_filters,
    )

    export_log.report_name = (
        report.title
    )

    export_log.started_at = (
        timezone.now()
    )

    export_log.save(
        update_fields=[
            "report_name",
            "started_at",
            "updated_at",
        ]
    )

    try:
        result = export_report(
            report_key=report.key,
            export_format=export_format,
            filters=normalized_filters,
            user=request.user,
            selected_columns=selected_columns,
            allow_empty=True,
        )

        export_log.file_name = (
            result.file_name
        )

        complete_export_log(
            export_log=export_log,
            content=result.content,
            records_count=(
                result.records_count
            ),
        )

    except Exception as exc:
        fail_export_log(
            export_log=export_log,
            exception=exc,
        )

        raise

    response = (
        result.to_http_response()
    )

    response[
        "X-Export-Log-ID"
    ] = str(
        export_log.pk
    )

    return response


def _queue_logged_export(
    request: HttpRequest,
    *,
    report: Any,
    export_format: str,
    filters: dict[str, Any],
    selected_columns: list[str] | None = None,
) -> HttpResponse:
    """Persist an export request and dispatch file generation to Celery."""
    normalized_filters = export_service.normalize_filters(filters)
    export_log = create_processing_log(
        request=request,
        module=report.module or report.key,
        report_key=report.key,
        file_name=_planned_file_name(report.key, export_format),
        export_format=export_format,
        filters=normalized_filters,
    )
    export_log.report_name = report.title
    export_log.status = ExportLog.ExportStatus.PENDING
    export_log.metadata = {"selected_columns": selected_columns or []}
    export_log.save(
        update_fields=[
            "report_name",
            "status",
            "metadata",
            "updated_at",
        ]
    )

    logger.info(
        "Export request queued.",
        extra={
            "event": "export_queued",
            "export_log_id": export_log.pk,
            "report_key": report.key,
            "user_id": request.user.pk,
        },
    )

    transaction.on_commit(
        lambda: build_export_file_task.delay(export_log.pk)
    )
    messages.info(request, "تمت جدولة التصدير. سيتاح الملف في سجل التصديرات عند اكتماله.")
    return redirect("exports_center:logs")


# ==========================================================
# لوحة مركز التصدير
# ==========================================================

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

    completed_logs = (
        ExportLog.objects.filter(
            status=(
                ExportLog
                .ExportStatus
                .SUCCESS
            ),
        )
    )

    today = timezone.localdate()

    total_logs = (
        ExportLog.objects.count()
    )

    successful_count = (
        completed_logs.count()
    )

    last_export = (
        completed_logs
        .order_by(
            "-completed_at"
        )
        .first()
    )

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
        "format_labels": (
            FORMAT_LABELS
        ),
        "total_reports": len(
            REPORT_REGISTRY
        ),
        "exports_today": (
            completed_logs.filter(
                created_at__date=today
            ).count()
        ),
        "active_export_users": (
            completed_logs
            .exclude(
                user=None
            )
            .values(
                "user_id"
            )
            .distinct()
            .count()
        ),
        "export_success_rate": (
            round(
                (
                    successful_count
                    / total_logs
                )
                * 100
            )
            if total_logs
            else 100
        ),
        "last_export_label": (
            last_export.report_name
            if last_export
            else "لا توجد عمليات بعد"
        ),
    }

    return render(
        request,
        "exports_center/dashboard.html",
        context,
    )


# ==========================================================
# صفحة الفلاتر
# ==========================================================

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

    filter_form_class = _create_report_filter_form_class(
        report.key,
    )
    filter_form = filter_form_class(
        request.GET
        or None
    )

    supported_formats = []

    for export_format in (
        FORMAT_EXCEL,
        FORMAT_PDF,
        FORMAT_CSV,
    ):
        if not report.supports_format(
            export_format
        ):
            continue

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
        "filter_form": filter_form,
        "supported_formats": (
            supported_formats
        ),
        "current_filters": (
            _extract_filters(
                request
            )
        ),
    }

    response = render(
        request,
        "exports_center/filters.html",
        context,
    )

    response[
        "X-Rendered-Template"
    ] = (
        "exports_center/filters.html"
    )

    return response


# ==========================================================
# صفحة معاينة التقرير
# ==========================================================

@login_required
@require_GET
def preview_view(
    request: HttpRequest,
    report_key: str,
) -> HttpResponse:
    """
    عرض صفحة معاينة التقرير.
    """

    started_at = time.perf_counter()

    report = _get_report_or_404(
        report_key
    )

    filters = export_service.normalize_filters(
        _extract_filters(
            request
        )
    )

    selected_columns = extract_selected_columns(
        request.GET
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
            user=request.user,
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

    export_columns = list(
        report.get_columns(
            FORMAT_EXCEL
        )
    )

    available_columns = build_available_columns(
        report=report,
        export_format=FORMAT_EXCEL,
    )

    if selected_columns is not None:
        selected_column_keys = set(
            selected_columns
        )

        for column in available_columns:
            column["selected"] = (
                column["key"]
                in selected_column_keys
            )

    internal_columns = (
        _build_preview_columns(
            export_columns
        )
    )

    preview_rows = (
        _build_preview_rows(
            records=list(
                preview_data[
                    "records"
                ]
            ),
            columns=internal_columns,
            start_number=1,
        )
    )

    public_columns = (
        _remove_private_column_data(
            internal_columns
        )
    )

    query_string = (
        _build_filter_query(
            filters,
            selected_columns=selected_columns,
        )
    )

    export_urls = (
        _build_export_urls(
            report=report,
            filters=filters,
            selected_columns=selected_columns,
        )
    )

    generated_at = (
        timezone.localtime()
    )

    generation_time_ms = round(
        (
            time.perf_counter()
            - started_at
        )
        * 1000,
        2,
    )

    estimated_size = (
        _estimate_preview_size(
            {
                "columns": (
                    public_columns
                ),
                "rows": (
                    preview_rows
                ),
            }
        )
    )

    supports_section_filter = any(
        str(
            getattr(
                report_filter,
                "parameter",
                "",
            )
            or ""
        ).strip() in {
            "section",
            "operational_section",
        }
        for report_filter in getattr(
            report,
            "filters",
            (),
        )
    )

    context = {
        "page_title": (
            f"معاينة {report.title}"
        ),
        "report": report,
        "report_key": report.key,
        "columns": public_columns,
        "available_columns": available_columns,
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
            preview_data.get(
                "indicators",
                {},
            )
        ),
        "filters": filters,
        "selected_columns": selected_columns,
        "supports_section_filter": (
            supports_section_filter
        ),
        "applied_filters": (
            _build_applied_filters_for_preview(
                report,
                filters,
            )
        ),
        "preview_limit": (
            preview_limit
        ),
        "export_urls": (
            export_urls
        ),
        "format_labels": (
            FORMAT_LABELS
        ),
        "query_string": (
            query_string
        ),
        "preview_data_url": reverse(
            "exports_center:preview-data",
            kwargs={
                "report_key": report.key,
            },
        ),
        "generated_at": (
            generated_at
        ),
        "generation_time_ms": (
            generation_time_ms
        ),
        "estimated_size": (
            estimated_size
        ),
        "allowed_page_sizes": sorted(
            ALLOWED_PAGE_SIZES
        ),
    }

    return render(
        request,
        "exports_center/preview.html",
        context,
    )


# ==========================================================
# بيانات المعاينة عبر Ajax
# ==========================================================

@login_required
@require_GET
def preview_data_view(
    request: HttpRequest,
    report_key: str,
) -> JsonResponse:
    """
    إرجاع بيانات المعاينة بصيغة JSON.

    يدعم:
    - البحث داخل البيانات.
    - ترتيب الأعمدة.
    - عدد السجلات في الصفحة.
    - ترقيم الصفحات.
    - بيانات وقت التوليد والحجم المتوقع.
    """

    started_at = time.perf_counter()

    report = _get_report_or_404(
        report_key
    )

    filters = export_service.normalize_filters(
        _extract_filters(
            request
        )
    )

    search_term = (
        _normalize_search_term(
            request.GET.get(
                "search"
            )
        )
    )

    sort_key = str(
        request.GET.get(
            "sort"
        )
        or ""
    ).strip()

    sort_direction = (
        _normalize_sort_direction(
            request.GET.get(
                "direction"
            )
        )
    )

    page = _normalize_page(
        request.GET.get(
            "page"
        )
    )

    page_size = (
        _normalize_page_size(
            request.GET.get(
                "page_size"
            )
        )
    )
    selected_columns = extract_selected_columns(
        request.GET
    )

    try:
        preview_data = preview_report(
            report_key=report.key,
            filters=filters,
            user=request.user,
            limit=(
                MAX_AJAX_PREVIEW_RECORDS
            ),
            selected_columns=selected_columns,
        )
        export_columns = list(
            select_export_columns(
                report=report,
                export_format=FORMAT_EXCEL,
                selected_columns=selected_columns,
                reject_unknown=True,
            )
        )

    except (
        ExportServiceError,
        ValidationError,
        ValueError,
        KeyError,
    ) as exc:
        logger.warning(
            "Preview Ajax request failed for report %s: %s",
            report.key,
            exc,
        )

        return JsonResponse(
            {
                "ok": False,
                "message": str(exc),
            },
            status=400,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    except Exception:
        logger.exception(
            "Unexpected preview Ajax error for report %s.",
            report.key,
        )

        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "حدث خطأ غير متوقع أثناء "
                    "تحميل بيانات المعاينة."
                ),
            },
            status=500,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    internal_columns = (
        _build_preview_columns(
            export_columns
        )
    )

    public_columns = (
        _remove_private_column_data(
            internal_columns
        )
    )

    all_rows = _build_preview_rows(
        records=list(
            preview_data[
                "records"
            ]
        ),
        columns=internal_columns,
        start_number=1,
    )

    filtered_rows = (
        _search_preview_rows(
            all_rows,
            search_term,
        )
    )

    allowed_sort_keys = {
        column["key"]
        for column in public_columns
    }

    filtered_rows = (
        _sort_preview_rows(
            filtered_rows,
            sort_key=sort_key,
            direction=sort_direction,
            allowed_keys=(
                allowed_sort_keys
            ),
        )
    )

    paginated_rows, pagination = (
        _paginate_preview_rows(
            filtered_rows,
            page=page,
            page_size=page_size,
        )
    )

    safe_rows = []

    for row in paginated_rows:
        safe_rows.append(
            {
                key: value
                for key, value
                in row.items()
                if key != "search_text"
            }
        )

    generated_at = (
        timezone.localtime()
    )

    generation_time_ms = round(
        (
            time.perf_counter()
            - started_at
        )
        * 1000,
        2,
    )

    response_payload = {
        "ok": True,
        "report": {
            "key": report.key,
            "title": report.title,
        },
        "columns": public_columns,
        "rows": safe_rows,
        "pagination": pagination,
        "search": search_term,
        "sorting": {
            "key": sort_key,
            "direction": (
                sort_direction
            ),
        },
        "summary": {
            "total_matching_records": (
                preview_data[
                    "records_count"
                ]
            ),
            "loaded_preview_records": len(
                all_rows
            ),
            "filtered_preview_records": len(
                filtered_rows
            ),
            "preview_window_limit": (
                MAX_AJAX_PREVIEW_RECORDS
            ),
            "is_preview_window_limited": (
                preview_data[
                    "records_count"
                ]
                > len(
                    all_rows
                )
            ),
        },
        "generated_at": (
            generated_at.isoformat()
        ),
        "generation_time_ms": (
            generation_time_ms
        ),
    }

    response_payload[
        "estimated_size"
    ] = _estimate_preview_size(
        response_payload
    )

    response = JsonResponse(
        response_payload,
        json_dumps_params={
            "ensure_ascii": False,
        },
    )

    response[
        "Cache-Control"
    ] = (
        "private, no-store, "
        "max-age=0"
    )

    response[
        "X-Content-Type-Options"
    ] = "nosniff"

    return response


# ==========================================================
# تنفيذ التصدير
# ==========================================================

@login_required
@require_POST
def export_view(
    request: HttpRequest,
    report_key: str,
    export_format: str,
) -> HttpResponse:
    """
    إنشاء وتنزيل التقرير مباشرة.
    """

    _require_export_permission(request)
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

    selected_columns = extract_selected_columns(
        request.POST
    )

    try:
        if settings.ASYNC_EXPORTS_ENABLED:
            return _queue_logged_export(
                request,
                report=report,
                export_format=normalized_format,
                filters=filters,
                selected_columns=selected_columns,
            )
        return _run_logged_export(
            request,
            report=report,
            export_format=(
                normalized_format
            ),
            filters=filters,
            selected_columns=selected_columns,
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
        logger.exception(
            "Unexpected export error for report %s.",
            report.key,
        )

        messages.error(
            request,
            (
                "حدث خطأ غير متوقع أثناء "
                "إنشاء التقرير."
            ),
        )

    query_string = (
        _build_filter_query(
            filters,
            selected_columns=selected_columns,
        )
    )

    preview_url = reverse(
        "exports_center:preview",
        kwargs={
            "report_key": report.key,
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


# ==========================================================
# التصدير من نموذج POST
# ==========================================================

@login_required
@require_POST
def export_submit_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    استقبال نموذج تصدير موحد.
    """

    _require_export_permission(request)
    report_key = (
        _normalize_report_key(
            request.POST.get(
                "report_key"
            )
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

    selected_columns = extract_selected_columns(
        request.POST
    )

    try:
        if settings.ASYNC_EXPORTS_ENABLED:
            return _queue_logged_export(
                request,
                report=report,
                export_format=export_format,
                filters=filters,
                selected_columns=selected_columns,
            )
        return _run_logged_export(
            request,
            report=report,
            export_format=(
                export_format
            ),
            filters=filters,
            selected_columns=selected_columns,
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

    except Exception:
        logger.exception(
            "Unexpected submitted export error for report %s.",
            report.key,
        )

        messages.error(
            request,
            "تعذر تنفيذ عملية التصدير.",
        )

    query_string = (
        _build_filter_query(
            filters,
            selected_columns=selected_columns,
        )
    )

    preview_url = reverse(
        "exports_center:preview",
        kwargs={
            "report_key": report.key,
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


# ==========================================================
# تنزيل نسخة محفوظة من التصدير
# ==========================================================

@login_required
@require_GET
def download_export_view(
    request: HttpRequest,
    export_log_id: int,
) -> HttpResponse:
    """
    تنزيل النسخة المؤسسية المحفوظة من ملف التصدير.
    """

    export_log = get_object_or_404(
        ExportLog.objects.filter(
            user=request.user,
        ),
        pk=export_log_id,
    )

    if not export_log.is_ready_for_download:
        raise Http404(
            "ملف التصدير غير متاح للتنزيل."
        )

    export_log.register_download()

    return FileResponse(
        export_log.file.open(
            "rb"
        ),
        as_attachment=True,
        filename=export_log.file_name,
    )


# ==========================================================
# سجل عمليات التصدير
# ==========================================================

@login_required
@require_GET
def logs_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    عرض سجل عمليات التصدير الحقيقي.
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

    _require_export_permission(request)
    logs = (
        ExportLog.objects
        .select_related(
            "user"
        )
        .filter(user=request.user)
    )

    if (
        status_filter
        in _valid_export_statuses()
    ):
        logs = logs.filter(
            status=status_filter
        )

    if (
        format_filter
        in _valid_export_formats()
    ):
        logs = logs.filter(
            export_format=(
                format_filter
            )
        )

    if module_filter:
        logs = logs.filter(
            module=module_filter
        )

    logs = logs.order_by(
        "-created_at",
        "-id",
    )

    all_logs = (
        ExportLog.objects.all()
    )

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
        "page_title": (
            "سجل عمليات التصدير"
        ),
        "logs": logs,
        "total_logs": total_logs,
        "excel_count": excel_count,
        "pdf_count": pdf_count,
        "csv_count": csv_count,
        "word_count": word_count,
        "success_count": (
            success_count
        ),
        "failed_count": failed_count,
        "processing_count": (
            processing_count
        ),
        "pending_count": pending_count,
        "selected_status": (
            status_filter
        ),
        "selected_format": (
            format_filter
        ),
        "selected_module": (
            module_filter
        ),
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
        "module_choices": (
            module_choices
        ),
    }

    return render(
        request,
        "exports_center/logs.html",
        context,
    )


# ==========================================================
# الصفحة المؤسسية
# ==========================================================

@require_http_methods(
    [
        "GET",
        "POST",
    ]
)
def institutional_view(
    request: HttpRequest,
) -> HttpResponse:
    """
    عرض صفحة مؤسسية مع نموذج تواصل.
    """

    if request.method == "POST":
        form = InstitutionalContactForm(
            request.POST
        )

        if form.is_valid():
            messages.success(
                request,
                (
                    "تم استلام رسالتك. "
                    "سنعاود التواصل قريبًا."
                ),
            )

            return redirect(
                "exports_center:institutional"
            )

    else:
        form = InstitutionalContactForm()

    context = {
        "page_title": "نبذة المؤسسة",
        "contact_form": form,
    }

    return render(
        request,
        "exports_center/institutional.html",
        context,
    )