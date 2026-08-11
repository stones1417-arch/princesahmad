from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from apps.exports_center.registry import (
    ExportColumn,
    ExportReportDefinition,
)


# ==========================================================
# الاستثناءات
# ==========================================================

class ColumnSelectionError(ValueError):
    """
    الخطأ الأساسي المتعلق باختيار أعمدة التصدير.
    """


class InvalidSelectedColumnsError(
    ColumnSelectionError
):
    """
    أسماء الأعمدة المحددة غير صحيحة.
    """


class NoColumnsSelectedError(
    ColumnSelectionError
):
    """
    لم يتم اختيار أي عمود صالح للتصدير.
    """


# ==========================================================
# الثوابت
# ==========================================================

MAX_SELECTED_COLUMNS = 100

CONTROL_COLUMN_NAMES = {
    "",
    "csrfmiddlewaretoken",
    "selected_columns",
    "columns",
    "column",
    "format",
    "export_format",
    "report_key",
    "page",
    "page_size",
    "preview_limit",
    "search",
    "sort",
    "direction",
    "action",
    "submit",
}


# ==========================================================
# أدوات قراءة تعريف العمود
# ==========================================================

def get_export_column_key(
    column: ExportColumn,
    *,
    fallback_index: int | None = None,
) -> str:
    """
    استخراج المفتاح المعتمد للعمود.

    ترتيب الاعتماد:
    1. key
    2. source
    3. اسم احتياطي مبني على رقم العمود

    يُفضّل أن يحتوي كل ExportColumn على key صريح.
    """

    possible_values = (
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
    )

    for value in possible_values:
        normalized_value = _normalize_column_name(
            value
        )

        if normalized_value:
            return normalized_value

    if fallback_index is not None:
        return f"column_{fallback_index}"

    return ""


def get_export_column_header(
    column: ExportColumn,
    *,
    fallback_index: int | None = None,
) -> str:
    """
    استخراج العنوان الظاهر للمستخدم.
    """

    possible_values = (
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
        getattr(
            column,
            "source",
            None,
        ),
    )

    for value in possible_values:
        normalized_value = str(
            value
            or ""
        ).strip()

        if normalized_value:
            return normalized_value

    if fallback_index is not None:
        return f"العمود {fallback_index}"

    return "عمود غير مسمى"


def build_available_columns(
    *,
    report: ExportReportDefinition,
    export_format: str,
) -> list[dict[str, Any]]:
    """
    تجهيز الأعمدة المتاحة للاستخدام في الواجهة.

    النتيجة مناسبة للإرسال إلى قالب Django أو JSON.
    """

    report_columns = tuple(
        report.get_columns(
            export_format
        )
    )

    available_columns: list[
        dict[str, Any]
    ] = []

    used_keys: set[str] = set()

    for index, column in enumerate(
        report_columns,
        start=1,
    ):
        column_key = get_export_column_key(
            column,
            fallback_index=index,
        )

        if not column_key:
            continue

        # منع المفاتيح المكررة من الظهور في الواجهة.
        if column_key in used_keys:
            continue

        used_keys.add(
            column_key
        )

        available_columns.append(
            {
                "key": column_key,
                "header": get_export_column_header(
                    column,
                    fallback_index=index,
                ),
                "source": str(
                    getattr(
                        column,
                        "source",
                        "",
                    )
                    or ""
                ).strip(),
                "width": getattr(
                    column,
                    "width",
                    None,
                ),
                "wrap_text": bool(
                    getattr(
                        column,
                        "wrap_text",
                        False,
                    )
                ),
                "number_format": str(
                    getattr(
                        column,
                        "number_format",
                        "",
                    )
                    or ""
                ).strip(),
                "selected": True,
                "position": index,
            }
        )

    return available_columns


# ==========================================================
# اختيار الأعمدة
# ==========================================================

def select_export_columns(
    *,
    report: ExportReportDefinition,
    export_format: str,
    selected_columns: (
        str
        | Sequence[str]
        | Iterable[str]
        | None
    ) = None,
    require_at_least_one: bool = True,
    reject_unknown: bool = False,
) -> tuple[ExportColumn, ...]:
    """
    اختيار أعمدة التقرير المسموح بها.

    السلوك:
    - إذا لم تُرسل selected_columns يتم استخدام جميع أعمدة التقرير.
    - يتم السماح فقط بالأعمدة الموجودة داخل تعريف التقرير.
    - يحافظ على الترتيب الذي اختاره المستخدم.
    - يمنع تكرار العمود.
    - لا يقبل أسماء أعمدة عشوائية.
    - يمكن رفض أي عمود غير معروف عبر reject_unknown=True.

    مثال:

        columns = select_export_columns(
            report=report,
            export_format="excel",
            selected_columns=[
                "full_name",
                "employee_number",
                "job_title",
            ],
        )
    """

    report_columns = tuple(
        report.get_columns(
            export_format
        )
    )

    if not report_columns:
        if require_at_least_one:
            raise NoColumnsSelectedError(
                "لا يحتوي التقرير على أعمدة متاحة "
                "للصيغة المطلوبة."
            )

        return ()

    normalized_selected_columns = (
        normalize_selected_columns(
            selected_columns
        )
    )

    # عدم اختيار المستخدم لأعمدة يعني استخدام الافتراضي كاملًا.
    if normalized_selected_columns is None:
        return report_columns

    if not normalized_selected_columns:
        if require_at_least_one:
            raise NoColumnsSelectedError(
                "يجب اختيار عمود واحد على الأقل "
                "قبل تنفيذ التصدير."
            )

        return ()

    if (
        len(normalized_selected_columns)
        > MAX_SELECTED_COLUMNS
    ):
        raise InvalidSelectedColumnsError(
            "عدد الأعمدة المحددة أكبر من الحد المسموح."
        )

    column_map: dict[
        str,
        ExportColumn
    ] = {}

    duplicate_report_keys: set[str] = set()

    for index, column in enumerate(
        report_columns,
        start=1,
    ):
        column_key = get_export_column_key(
            column,
            fallback_index=index,
        )

        if not column_key:
            continue

        if column_key in column_map:
            duplicate_report_keys.add(
                column_key
            )

            continue

        column_map[column_key] = column

    if duplicate_report_keys:
        duplicated_names = "، ".join(
            sorted(
                duplicate_report_keys
            )
        )

        raise InvalidSelectedColumnsError(
            "تعريف التقرير يحتوي على مفاتيح "
            "أعمدة مكررة: "
            f"{duplicated_names}"
        )

    selected_result: list[
        ExportColumn
    ] = []

    unknown_columns: list[str] = []

    used_selected_keys: set[str] = set()

    for selected_key in normalized_selected_columns:
        if selected_key in used_selected_keys:
            continue

        used_selected_keys.add(
            selected_key
        )

        matched_column = column_map.get(
            selected_key
        )

        if matched_column is None:
            unknown_columns.append(
                selected_key
            )

            continue

        selected_result.append(
            matched_column
        )

    if (
        reject_unknown
        and unknown_columns
    ):
        unknown_names = "، ".join(
            unknown_columns
        )

        raise InvalidSelectedColumnsError(
            "توجد أعمدة غير صالحة أو غير مسموحة: "
            f"{unknown_names}"
        )

    if (
        not selected_result
        and require_at_least_one
    ):
        raise NoColumnsSelectedError(
            "لم يتم العثور على أي عمود صالح "
            "ضمن الأعمدة المحددة."
        )

    return tuple(
        selected_result
    )


# ==========================================================
# تطبيع المدخلات
# ==========================================================

def normalize_selected_columns(
    selected_columns: (
        str
        | Sequence[str]
        | Iterable[str]
        | None
    ),
) -> list[str] | None:
    """
    تحويل مدخل الأعمدة إلى قائمة نظيفة.

    يدعم:
    - None
    - نص مفرد
    - نص مفصول بفواصل
    - قائمة
    - tuple
    - set
    - QueryDict.getlist الناتج من Django

    أمثلة مقبولة:

        "full_name"

        "full_name,employee_number"

        [
            "full_name",
            "employee_number",
        ]
    """

    if selected_columns is None:
        return None

    raw_values: list[Any] = []

    if isinstance(
        selected_columns,
        str,
    ):
        raw_values.extend(
            _split_column_string(
                selected_columns
            )
        )

    else:
        try:
            for value in selected_columns:
                if isinstance(
                    value,
                    str,
                ):
                    raw_values.extend(
                        _split_column_string(
                            value
                        )
                    )

                else:
                    raw_values.append(
                        value
                    )

        except TypeError as exc:
            raise InvalidSelectedColumnsError(
                "صيغة الأعمدة المحددة غير صحيحة."
            ) from exc

    normalized_columns: list[str] = []

    used_columns: set[str] = set()

    for raw_value in raw_values:
        column_name = _normalize_column_name(
            raw_value
        )

        if not column_name:
            continue

        if column_name in CONTROL_COLUMN_NAMES:
            continue

        if column_name in used_columns:
            continue

        used_columns.add(
            column_name
        )

        normalized_columns.append(
            column_name
        )

    return normalized_columns


def extract_selected_columns(
    source: Any,
    *,
    field_name: str = "selected_columns",
) -> list[str] | None:
    """
    استخراج الأعمدة من request.GET أو request.POST أو dict.

    يدعم حالات مثل:

        ?selected_columns=full_name
        &selected_columns=employee_number

    ويدعم أيضًا:

        ?selected_columns=full_name,employee_number
    """

    if source is None:
        return None

    getlist_method = getattr(
        source,
        "getlist",
        None,
    )

    if callable(
        getlist_method
    ):
        values = getlist_method(
            field_name
        )

        if not values:
            alternative_values = (
                getlist_method(
                    "columns"
                )
            )

            values = alternative_values

        if not values:
            return None

        return normalize_selected_columns(
            values
        )

    if isinstance(
        source,
        dict,
    ):
        value = source.get(
            field_name
        )

        if value is None:
            value = source.get(
                "columns"
            )

        return normalize_selected_columns(
            value
        )

    get_method = getattr(
        source,
        "get",
        None,
    )

    if callable(
        get_method
    ):
        value = get_method(
            field_name
        )

        if value is None:
            value = get_method(
                "columns"
            )

        return normalize_selected_columns(
            value
        )

    return None


# ==========================================================
# أدوات التحقق
# ==========================================================

def validate_selected_columns(
    *,
    report: ExportReportDefinition,
    export_format: str,
    selected_columns: (
        str
        | Sequence[str]
        | Iterable[str]
        | None
    ),
) -> list[str]:
    """
    التحقق من الأعمدة وإرجاع مفاتيحها المعتمدة.

    يتم رفض أي اسم غير موجود في تعريف التقرير.
    """

    columns = select_export_columns(
        report=report,
        export_format=export_format,
        selected_columns=selected_columns,
        require_at_least_one=True,
        reject_unknown=True,
    )

    return [
        get_export_column_key(
            column,
            fallback_index=index,
        )
        for index, column in enumerate(
            columns,
            start=1,
        )
    ]


def get_selected_column_headers(
    *,
    report: ExportReportDefinition,
    export_format: str,
    selected_columns: (
        str
        | Sequence[str]
        | Iterable[str]
        | None
    ) = None,
) -> list[dict[str, str]]:
    """
    إرجاع مفاتيح وعناوين الأعمدة المختارة.

    مناسب لإظهار ملخص الاختيار في الواجهة.
    """

    columns = select_export_columns(
        report=report,
        export_format=export_format,
        selected_columns=selected_columns,
        require_at_least_one=True,
        reject_unknown=False,
    )

    return [
        {
            "key": get_export_column_key(
                column,
                fallback_index=index,
            ),
            "header": get_export_column_header(
                column,
                fallback_index=index,
            ),
        }
        for index, column in enumerate(
            columns,
            start=1,
        )
    ]


# ==========================================================
# أدوات داخلية
# ==========================================================

def _split_column_string(
    value: str,
) -> list[str]:
    """
    تقسيم النص باستخدام الفاصلة الإنجليزية أو العربية.
    """

    normalized_value = str(
        value
        or ""
    ).replace(
        "،",
        ",",
    )

    return [
        item
        for item in normalized_value.split(
            ","
        )
    ]


def _normalize_column_name(
    value: Any,
) -> str:
    """
    تنظيف اسم العمود.

    يسمح بالأحرف والأرقام والنقطة والشرطة السفلية فقط.
    """

    normalized_value = str(
        value
        or ""
    ).strip()

    if not normalized_value:
        return ""

    # حماية إضافية من مدخلات غير متوقعة.
    if len(
        normalized_value
    ) > 200:
        raise InvalidSelectedColumnsError(
            "اسم العمود يتجاوز الطول المسموح."
        )

    allowed_characters = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "._-"
    )

    if any(
        character not in allowed_characters
        for character in normalized_value
    ):
        raise InvalidSelectedColumnsError(
            "اسم العمود يحتوي على محارف غير مسموحة: "
            f"{normalized_value}"
        )

    return normalized_value