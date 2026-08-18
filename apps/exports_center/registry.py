from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from apps.exports_center.definitions.doors import (
    DOORS_COLUMNS_DEFINITION,
    DOORS_FILTERS_DEFINITION,
)
from apps.exports_center.definitions.employees import (
    EMPLOYEES_COLUMNS_DEFINITION,
    EMPLOYEES_FILTERS_DEFINITION,
)
from apps.exports_center.definitions.incidents import (
    INCIDENTS_COLUMNS_DEFINITION,
    INCIDENTS_FILTERS_DEFINITION,
)
from apps.exports_center.definitions.maintenance import (
    MAINTENANCE_COLUMNS_DEFINITION,
)
from apps.hr.models import Employee
from apps.exports_center.definitions.reports import (
    REPORTS_COLUMNS_DEFINITION,
)
from apps.roles.services.permission_registry import (
    PlatformPermissions,
)


# ==================================================
# صيغ التصدير المدعومة
# ==================================================

FORMAT_EXCEL = "excel"
FORMAT_PDF = "pdf"
FORMAT_CSV = "csv"
FORMAT_WORD = "word"

SUPPORTED_EXPORT_FORMATS = (
    FORMAT_EXCEL,
    FORMAT_PDF,
    FORMAT_CSV,
)


# ==================================================
# اتجاهات أبواب المسجد الحرام
# ==================================================

DOOR_DIRECTION_CHOICES = (
    ("south", "الجهة الجنوبية"),
    ("west", "الجهة الغربية"),
    ("north", "الجهة الشمالية"),
    ("east", "الجهة الشرقية"),
    ("southeast", "الجهة الجنوبية الشرقية"),
)


DOOR_DIRECTION_NUMBERS = {
    "south": {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6B",
    },
    "west": {
        "6A",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "13",
        "14",
    },
    "north": {
        str(number)
        for number in range(15, 28)
    },
    "east": {
        str(number)
        for number in range(28, 36)
    },
    "southeast": {
        str(number)
        for number in range(36, 42)
    },
}


DOOR_DIRECTION_LABELS = dict(
    DOOR_DIRECTION_CHOICES
)

SECTION_LABELS = {
    key: value
    for key, value in (
        MAINTENANCE_COLUMNS_DEFINITION[0]
        .get("section_labels", {})
        .items()
    )
}

SECTION_LABELS.update(
    {
        "male": "رجالي",
        "female": "نسائي",
        "shared": "رجالي ونسائي",
    }
)

SECTION_LABELS.update(
    {
        # توافق خلفي للقيم الفارغة أو غير المعروفة.
        "": "غير محدد",
    }
)


def _find_definition_entry(
    definition: tuple[dict[str, Any], ...],
    key: str,
) -> dict[str, Any]:
    """
    إرجاع عنصر تعريف حسب المفتاح مع fallback آمن.
    """
    for entry in definition:
        if str(entry.get("key", "")).strip() == key:
            return entry

    return {}


def _definition_choices(
    definition: tuple[dict[str, Any], ...],
    key: str,
    fallback: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """
    قراءة choices من التعريف المعياري.
    """
    entry = _find_definition_entry(
        definition,
        key,
    )

    raw_choices = entry.get("choices")
    if not raw_choices:
        return fallback

    return tuple(
        (
            str(choice_key),
            str(choice_label),
        )
        for choice_key, choice_label in raw_choices
    )


def _definition_header(
    definition: tuple[dict[str, Any], ...],
    key: str,
    fallback: str,
) -> str:
    """
    قراءة عنوان العمود من التعريف المعياري.
    """
    entry = _find_definition_entry(
        definition,
        key,
    )

    return str(
        entry.get("header")
        or fallback
    )


# ==================================================
# أنواع الحقول المدعومة في الفلاتر
# ==================================================

FILTER_TYPE_TEXT = "text"
FILTER_TYPE_DATE = "date"
FILTER_TYPE_CHOICE = "choice"
FILTER_TYPE_MODEL = "model"
FILTER_TYPE_BOOLEAN = "boolean"


# ==================================================
# تعريف عمود التصدير
# ==================================================

@dataclass(frozen=True)
class ExportColumn:
    """
    تعريف عمود موحد يستخدم في Excel وPDF وCSV.

    source:
        اسم الحقل أو مساره مثل:
        employee.full_name
        shift_plan.shift_type.name

    getter:
        دالة اختيارية لاستخراج قيمة مخصصة.

    width:
        عرض العمود في Excel.

    wrap_text:
        التفاف النصوص الطويلة.

    include_in:
        الصيغ التي يظهر فيها العمود.
    """

    key: str
    header: str
    source: str | None = None
    getter: Callable[[Any], Any] | None = None
    width: float = 18
    wrap_text: bool = False
    number_format: str | None = None
    css_class: str = ""
    include_in: tuple[str, ...] = SUPPORTED_EXPORT_FORMATS

    def get_value(
        self,
        instance: Any,
    ) -> Any:
        """
        استخراج قيمة العمود من السجل.
        """
        if self.getter:
            try:
                return self.getter(instance)
            except (
                AttributeError,
                TypeError,
                ValueError,
            ):
                return ""

        if not self.source:
            return ""

        value = instance

        for attribute_name in self.source.split("."):
            if value is None:
                return ""

            value = getattr(
                value,
                attribute_name,
                "",
            )

            if callable(value):
                try:
                    value = value()
                except (
                    AttributeError,
                    TypeError,
                    ValueError,
                ):
                    return ""

        return (
            ""
            if value is None
            else value
        )

    def supports_format(
        self,
        export_format: str,
    ) -> bool:
        return export_format in self.include_in


# ==================================================
# تعريف فلتر التصدير
# ==================================================

@dataclass(frozen=True)
class ExportFilter:
    """
    تعريف فلتر يظهر للمستخدم في مركز التصدير.
    """

    key: str
    label: str
    filter_type: str
    parameter: str | None = None
    choices: tuple[
        tuple[str, str],
        ...
    ] = ()
    placeholder: str = ""
    required: bool = False


# ==================================================
# تعريف ورقة Excel
# ==================================================

@dataclass(frozen=True)
class ExportSheet:
    """
    تعريف ورقة داخل ملف Excel.

    selector_key:
        اسم المحدد المسؤول عن جلب البيانات.

    sheet_type:
        data للبيانات.
        indicators للمؤشرات.
        summary للملخص.
    """

    key: str
    title: str
    selector_key: str
    columns: tuple[ExportColumn, ...] = ()
    sheet_type: str = "data"


# ==================================================
# تعريف التقرير
# ==================================================

@dataclass(frozen=True)
class ExportReportDefinition:
    """
    تعريف كامل لنوع تقرير داخل مركز التصدير.
    """

    key: str
    title: str
    module: str
    description: str
    icon: str

    selector_key: str

    columns: tuple[
        ExportColumn,
        ...
    ]

    permission: str = (
        PlatformPermissions.EXPORT_REPORT
    )

    supported_formats: tuple[
        str,
        ...
    ] = SUPPORTED_EXPORT_FORMATS

    filters: tuple[
        ExportFilter,
        ...
    ] = ()

    sheets: tuple[
        ExportSheet,
        ...
    ] = ()

    template_name: str = (
        "exports_center/pdf/official_report.html"
    )

    landscape: bool = True

    include_indicators: bool = False
    include_summary: bool = False
    include_recommendations: bool = False
    include_approval: bool = False

    default_filename: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def supports_format(
        self,
        export_format: str,
    ) -> bool:
        return (
            export_format
            in self.supported_formats
        )

    def get_columns(
        self,
        export_format: str,
    ) -> tuple[ExportColumn, ...]:
        """
        إرجاع الأعمدة المناسبة للصيغة المحددة.
        """
        return tuple(
            column
            for column in self.columns
            if column.supports_format(
                export_format
            )
        )

    @property
    def filename_prefix(self) -> str:
        return (
            self.default_filename
            or self.key
        )


# ==================================================
# دوال تنسيق مشتركة
# ==================================================

def yes_no(
    value: Any,
) -> str:
    return "نعم" if bool(value) else "لا"


def safe_text(
    value: Any,
) -> str:
    return (
        ""
        if value is None
        else str(value)
    )


def display_user(
    user: Any,
) -> str:
    if not user:
        return ""

    get_full_name = getattr(
        user,
        "get_full_name",
        None,
    )

    if callable(get_full_name):
        full_name = (
            get_full_name()
            or ""
        ).strip()

        if full_name:
            return full_name

    return getattr(
        user,
        "username",
        "",
    )


def display_method(
    instance: Any,
    method_name: str,
) -> str:
    method = getattr(
        instance,
        method_name,
        None,
    )

    if not callable(method):
        return ""

    try:
        return safe_text(
            method()
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
    ):
        return ""


def format_date(
    value: Any,
) -> str:
    if not value:
        return ""

    if hasattr(value, "strftime"):
        return value.strftime(
            "%Y-%m-%d"
        )

    return safe_text(value)


def format_datetime(
    value: Any,
) -> str:
    if not value:
        return ""

    if hasattr(value, "strftime"):
        return value.strftime(
            "%Y-%m-%d %H:%M"
        )

    return safe_text(value)


def get_door_direction(
    door_number: Any,
) -> str:
    """
    إرجاع اسم جهة الباب من رقمه.
    """
    normalized_number = (
        safe_text(door_number)
        .strip()
        .upper()
    )

    for (
        direction_key,
        numbers,
    ) in DOOR_DIRECTION_NUMBERS.items():
        if normalized_number in numbers:
            return DOOR_DIRECTION_LABELS.get(
                direction_key,
                direction_key,
            )

    return "غير محدد"


def format_section_label(
    value: Any,
) -> str:
    """
    إرجاع الوصف العربي للقسم التشغيلي.
    """
    section_key = safe_text(value).strip().lower()

    return SECTION_LABELS.get(
        section_key,
        "غير محدد",
    )


# ==================================================
# الفلاتر المشتركة
# ==================================================

DATE_RANGE_FILTERS = (
    ExportFilter(
        key="date_from",
        label="من تاريخ",
        filter_type=FILTER_TYPE_DATE,
        parameter="date_from",
    ),
    ExportFilter(
        key="date_to",
        label="إلى تاريخ",
        filter_type=FILTER_TYPE_DATE,
        parameter="date_to",
    ),
)


SHIFT_FILTER = ExportFilter(
    key="shift_plan",
    label="الوردية",
    filter_type=FILTER_TYPE_MODEL,
    parameter="shift_plan",
)


EMPLOYEE_FILTER = ExportFilter(
    key="employee",
    label="الموظف",
    filter_type=FILTER_TYPE_MODEL,
    parameter="employee",
)


ZONE_FILTER = ExportFilter(
    key="zone",
    label="المنطقة",
    filter_type=FILTER_TYPE_MODEL,
    parameter="zone",
)


DOOR_DIRECTION_FILTER = ExportFilter(
    key="door_direction",
    label="جهة الأبواب",
    filter_type=FILTER_TYPE_CHOICE,
    parameter="door_direction",
    choices=DOOR_DIRECTION_CHOICES,
)


ACTIVE_FILTER = ExportFilter(
    key="is_active",
    label="حالة التفعيل",
    filter_type=FILTER_TYPE_CHOICE,
    parameter="is_active",
    choices=(
        ("true", "نشط"),
        ("false", "غير نشط"),
    ),
)

SECTION_FILTER = ExportFilter(
    key="section",
    label="القسم التشغيلي",
    filter_type=FILTER_TYPE_CHOICE,
    parameter="section",
    choices=_definition_choices(
        INCIDENTS_FILTERS_DEFINITION,
        "section",
        (
            ("all", "الكل"),
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
    ),
)

OPERATIONAL_SECTION_FILTER = ExportFilter(
    key="operational_section",
    label="القسم التشغيلي",
    filter_type=FILTER_TYPE_CHOICE,
    parameter="operational_section",
    choices=_definition_choices(
        DOORS_FILTERS_DEFINITION,
        "operational_section",
        (
            ("all", "الكل"),
            ("male", "رجالي"),
            ("female", "نسائي"),
            ("shared", "مشترك"),
        ),
    ),
)


# ==================================================
# أعمدة الموظفين
# ==================================================

EMPLOYEE_COLUMNS = (
    ExportColumn(
        key="employee_number",
        header="الرقم الوظيفي",
        source="employee_number",
        width=16,
    ),
    ExportColumn(
        key="full_name",
        header="الاسم الكامل",
        source="full_name",
        width=28,
    ),
    ExportColumn(
        key="operational_section",
        header=_definition_header(
            EMPLOYEES_COLUMNS_DEFINITION,
            "operational_section",
            "القسم التشغيلي",
        ),
        getter=lambda item: display_method(
            item,
            "get_operational_section_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="national_id",
        header="رقم الهوية",
        source="national_id",
        width=18,
    ),
    ExportColumn(
        key="phone_number",
        header="رقم الجوال",
        source="phone_number",
        width=18,
    ),
    ExportColumn(
        key="email",
        header="البريد الإلكتروني",
        source="email",
        width=28,
    ),
    ExportColumn(
        key="job_title",
        header="المسمى الوظيفي",
        getter=lambda item: display_method(
            item,
            "get_job_title_display",
        ),
        width=24,
    ),
    ExportColumn(
        key="work_status",
        header="حالة الموظف",
        getter=lambda item: display_method(
            item,
            "get_work_status_display",
        ),
        width=18,
    ),
    ExportColumn(
        key="is_active",
        header="نشط في النظام",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_active",
                False,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="can_work_on_doors",
        header="يمكن تسكينه على الأبواب",
        getter=lambda item: yes_no(
            getattr(
                item,
                "can_work_on_doors",
                False,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="can_execute_maintenance",
        header="يمكنه تنفيذ الصيانة",
        getter=lambda item: yes_no(
            getattr(
                item,
                "can_execute_maintenance",
                False,
            )
        ),
        width=21,
    ),
    ExportColumn(
        key="hire_date",
        header="تاريخ المباشرة",
        getter=lambda item: format_date(
            getattr(
                item,
                "hire_date",
                None,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="notes",
        header="ملاحظات",
        source="notes",
        width=34,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة تسكين الموظفين
# ==================================================

SHIFT_ASSIGNMENT_COLUMNS = (
    ExportColumn(
        key="shift_name",
        header="الوردية",
        source="shift_plan.shift_type.name",
        width=20,
    ),
    ExportColumn(
        key="shift_date",
        header="تاريخ الوردية",
        getter=lambda item: format_date(
            getattr(
                getattr(
                    item,
                    "shift_plan",
                    None,
                ),
                "date",
                None,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="employee_name",
        header="الموظف",
        source="employee.full_name",
        width=28,
    ),
    ExportColumn(
        key="employee_number",
        header="الرقم الوظيفي",
        source="employee.employee_number",
        width=16,
    ),
    ExportColumn(
        key="role",
        header="الدور التشغيلي",
        getter=lambda item: display_method(
            item,
            "get_role_display",
        ),
        width=20,
    ),
    ExportColumn(
        key="is_confirmed",
        header="تم التأكيد",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_confirmed",
                False,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="notes",
        header="ملاحظات",
        source="notes",
        width=32,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة توزيع الأبواب
# ==================================================

DOOR_DISTRIBUTION_COLUMNS = (
    ExportColumn(
        key="shift_name",
        header="الوردية",
        source="shift_plan.shift_type.name",
        width=20,
    ),
    ExportColumn(
        key="shift_date",
        header="تاريخ الوردية",
        getter=lambda item: format_date(
            getattr(
                getattr(
                    item,
                    "shift_plan",
                    None,
                ),
                "date",
                None,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="door_number",
        header="رقم الباب",
        getter=lambda item: getattr(
            getattr(
                item,
                "door",
                None,
            ),
            "door_number",
            "",
        ),
        width=14,
    ),
    ExportColumn(
        key="door_name",
        header="اسم الباب",
        source="door.name",
        width=22,
    ),
    ExportColumn(
        key="section",
        header="القسم التشغيلي",
        getter=lambda item: display_method(
            item,
            "get_section_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="door_direction",
        header="جهة الباب",
        getter=lambda item: get_door_direction(
            getattr(
                getattr(
                    item,
                    "door",
                    None,
                ),
                "door_number",
                "",
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="employee_name",
        header="الموظف",
        source="employee.full_name",
        width=28,
    ),
    ExportColumn(
        key="employee_number",
        header="الرقم الوظيفي",
        source="employee.employee_number",
        width=16,
    ),
    ExportColumn(
        key="role",
        header="الدور",
        getter=lambda item: display_method(
            item,
            "get_role_display",
        ),
        width=18,
    ),
    ExportColumn(
        key="is_supervisor",
        header="مشرف الباب",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_supervisor",
                False,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="is_active",
        header="نشط",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_active",
                False,
            )
        ),
        width=12,
    ),
    ExportColumn(
        key="notes",
        header="ملاحظات",
        source="notes",
        width=32,
        wrap_text=True,
    ),
    ExportColumn(
        key="assigned_at",
        header="تاريخ التوزيع",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "assigned_at",
                None,
            )
        ),
        width=20,
    ),
)


# ==================================================
# أعمدة المواقع والأبواب
# ==================================================

LOCATION_COLUMNS = (
    ExportColumn(
        key="door_number",
        header="رقم الباب",
        source="door_number",
        width=14,
    ),
    ExportColumn(
        key="door_name",
        header="اسم الباب",
        source="name",
        width=24,
    ),
    ExportColumn(
        key="zone",
        header="المنطقة",
        source="zone.name",
        width=22,
    ),
    ExportColumn(
        key="operational_section",
        header=_definition_header(
            DOORS_COLUMNS_DEFINITION,
            "operational_section",
            "القسم التشغيلي",
        ),
        getter=lambda item: display_method(
            item,
            "get_operational_section_display",
        ),
        width=18,
    ),
    ExportColumn(
        key="direction",
        header="جهة الباب",
        getter=lambda item: get_door_direction(
            getattr(
                item,
                "door_number",
                "",
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="is_active",
        header="نشط",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_active",
                False,
            )
        ),
        width=12,
    ),
    ExportColumn(
        key="notes",
        header="ملاحظات",
        source="notes",
        width=36,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة الراحات
# ==================================================

BREAK_COLUMNS = (
    ExportColumn(
        key="employee_name",
        header="الموظف",
        source="employee.full_name",
        width=28,
    ),
    ExportColumn(
        key="employee_number",
        header="الرقم الوظيفي",
        source="employee.employee_number",
        width=16,
    ),
    ExportColumn(
        key="operational_section",
        header="القسم التشغيلي",
        source="operational_section_label",
        width=16,
    ),
    ExportColumn(
        key="shift_type",
        header="نوع الوردية",
        source="shift_type.name",
        width=20,
    ),
    ExportColumn(
        key="job_title",
        header="المسمى في الوردية",
        getter=lambda item: display_method(
            item,
            "get_job_title_display",
        ),
        width=22,
    ),
    ExportColumn(
        key="rest_days",
        header="أيام الراحة",
        getter=lambda item: display_method(
            item,
            "get_rest_days_display",
        ),
        width=20,
    ),
    ExportColumn(
        key="is_active",
        header="نشط",
        getter=lambda item: yes_no(
            getattr(
                item,
                "is_active",
                False,
            )
        ),
        width=12,
    ),
    ExportColumn(
        key="notes",
        header="ملاحظات",
        source="notes",
        width=32,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة البلاغات
# ==================================================

INCIDENT_COLUMNS = (
    ExportColumn(
        key="incident_number",
        header="رقم البلاغ",
        source="incident_number",
        width=18,
    ),
    ExportColumn(
        key="incident_type",
        header="نوع البلاغ",
        getter=lambda item: display_method(
            item,
            "get_incident_type_display",
        ),
        width=20,
    ),
    ExportColumn(
        key="priority",
        header="الأولوية",
        getter=lambda item: display_method(
            item,
            "get_priority_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="status",
        header="الحالة",
        getter=lambda item: display_method(
            item,
            "get_status_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="shift_name",
        header="الوردية",
        source="shift_plan.shift_type.name",
        width=20,
    ),
    ExportColumn(
        key="door_number",
        header="رقم الباب",
        source="door_shift.door_number",
        width=14,
    ),
    ExportColumn(
        key="section",
        header=_definition_header(
            INCIDENTS_COLUMNS_DEFINITION,
            "section",
            "القسم التشغيلي",
        ),
        getter=lambda item: format_section_label(
            getattr(
                item,
                "section",
                "",
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="description",
        header="وصف البلاغ",
        source="description",
        width=42,
        wrap_text=True,
    ),
    ExportColumn(
        key="reported_by",
        header="اسم المبلغ",
        source="reported_by_name",
        width=24,
    ),
    ExportColumn(
        key="created_by",
        header="أنشئ بواسطة",
        getter=lambda item: display_user(
            getattr(
                item,
                "created_by",
                None,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="created_at",
        header="تاريخ الإنشاء",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "created_at",
                None,
            )
        ),
        width=20,
    ),
    ExportColumn(
        key="closing_notes",
        header="ملاحظات الإغلاق",
        source="closing_notes",
        width=36,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة الصيانة
# ==================================================

MAINTENANCE_COLUMNS = (
    ExportColumn(
        key="request_number",
        header="رقم الطلب",
        source="request_number",
        width=18,
    ),
    ExportColumn(
        key="door_number",
        header="رقم الباب",
        source="door_shift.door_number",
        width=14,
    ),
    ExportColumn(
        key="shift_name",
        header="الوردية",
        source="door_shift.shift_plan.shift_type.name",
        width=20,
    ),
    ExportColumn(
        key="section",
        header=_definition_header(
            REPORTS_COLUMNS_DEFINITION,
            "section",
            "القسم التشغيلي",
        ),
        getter=lambda item: format_section_label(
            getattr(
                item,
                "section",
                "",
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="description",
        header="وصف المشكلة",
        source="description",
        width=42,
        wrap_text=True,
    ),
    ExportColumn(
        key="priority",
        header="درجة الخطورة",
        getter=lambda item: display_method(
            item,
            "get_priority_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="status",
        header="حالة الطلب",
        getter=lambda item: display_method(
            item,
            "get_status_display",
        ),
        width=18,
    ),
    ExportColumn(
        key="technician",
        header="الفني المكلف",
        getter=lambda item: (
            display_user(
                getattr(
                    item,
                    "technician",
                    None,
                )
            )
            or getattr(
                item,
                "technician_name",
                "",
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="created_by",
        header="أنشئ بواسطة",
        getter=lambda item: display_user(
            getattr(
                item,
                "created_by",
                None,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="created_at",
        header="تاريخ الإنشاء",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "created_at",
                None,
            )
        ),
        width=20,
    ),
    ExportColumn(
        key="closed_at",
        header="تاريخ الإغلاق",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "closed_at",
                None,
            )
        ),
        width=20,
    ),
    ExportColumn(
        key="closing_notes",
        header="ملاحظات الإغلاق",
        source="closing_notes",
        width=36,
        wrap_text=True,
    ),
)


# ==================================================
# أعمدة التقارير
# ==================================================

REPORT_COLUMNS = (
    ExportColumn(
        key="report_number",
        header="رقم التقرير",
        source="report_number",
        width=20,
    ),
    ExportColumn(
        key="report_type",
        header="نوع التقرير",
        getter=lambda item: display_method(
            item,
            "get_report_type_display",
        ),
        width=20,
    ),
    ExportColumn(
        key="status",
        header="الحالة",
        getter=lambda item: display_method(
            item,
            "get_status_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="shift_name",
        header="الوردية",
        source="shift_plan.shift_type.name",
        width=18,
    ),
    ExportColumn(
        key="shift_date",
        header="تاريخ الوردية",
        getter=lambda item: format_date(
            getattr(
                getattr(
                    item,
                    "shift_plan",
                    None,
                ),
                "date",
                None,
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="section",
        header="القسم التشغيلي",
        getter=lambda item: format_section_label(
            getattr(
                item,
                "section",
                "",
            )
        ),
        width=16,
    ),
    ExportColumn(
        key="total_doors",
        header="إجمالي الأبواب",
        source="total_doors",
        width=16,
    ),
    ExportColumn(
        key="open_doors",
        header="الأبواب المفتوحة",
        source="open_doors",
        width=17,
    ),
    ExportColumn(
        key="closed_doors",
        header="الأبواب المغلقة",
        source="closed_doors",
        width=17,
    ),
    ExportColumn(
        key="maintenance_doors",
        header="أبواب تحت الصيانة",
        source="maintenance_doors",
        width=20,
    ),
    ExportColumn(
        key="total_employees",
        header="عدد الموظفين",
        source="total_employees",
        width=16,
    ),
    ExportColumn(
        key="total_maintenance_requests",
        header="طلبات الصيانة",
        source="total_maintenance_requests",
        width=18,
    ),
    ExportColumn(
        key="summary",
        header="الملخص التنفيذي",
        source="summary",
        width=44,
        wrap_text=True,
    ),
    ExportColumn(
        key="recommendations",
        header="التوصيات",
        source="recommendations",
        width=44,
        wrap_text=True,
    ),
    ExportColumn(
        key="created_by",
        header="أنشئ بواسطة",
        getter=lambda item: display_user(
            getattr(
                item,
                "created_by",
                None,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="approved_by",
        header="اعتمد بواسطة",
        getter=lambda item: display_user(
            getattr(
                item,
                "approved_by",
                None,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="created_at",
        header="تاريخ الإنشاء",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "created_at",
                None,
            )
        ),
        width=20,
    ),
)


# ==================================================
# أعمدة التعاميم
# ==================================================

ANNOUNCEMENT_COLUMNS = (
    ExportColumn(
        key="title",
        header="العنوان",
        source="title",
        width=28,
    ),
    ExportColumn(
        key="content",
        header="المحتوى",
        source="content",
        width=50,
        wrap_text=True,
    ),
    ExportColumn(
        key="priority",
        header="الأولوية",
        getter=lambda item: display_method(
            item,
            "get_priority_display",
        ),
        width=16,
    ),
    ExportColumn(
        key="is_active",
        header="الحالة",
        getter=lambda item: (
            "نشط"
            if getattr(
                item,
                "is_active",
                False,
            )
            else "معطل"
        ),
        width=14,
    ),
    ExportColumn(
        key="created_by",
        header="المنشئ",
        getter=lambda item: display_user(
            getattr(
                item,
                "created_by",
                None,
            )
        ),
        width=22,
    ),
    ExportColumn(
        key="created_at",
        header="تاريخ الإنشاء",
        getter=lambda item: format_datetime(
            getattr(
                item,
                "created_at",
                None,
            )
        ),
        width=20,
    ),
)


# ==================================================
# سجل التقارير
# ==================================================

REPORT_REGISTRY: dict[
    str,
    ExportReportDefinition,
] = {
    "employees": ExportReportDefinition(
        key="employees",
        title="سجل الموظفين",
        module="الموارد البشرية",
        description=(
            "بيانات الموظفين والمسميات "
            "والحالات ووسائل التواصل."
        ),
        icon="users",
        selector_key="employees",
        columns=EMPLOYEE_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            ExportFilter(
                key="job_title",
                label="المسمى الوظيفي",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="job_title",
            ),
            ExportFilter(
                key="operational_section",
                label="القسم التشغيلي",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="operational_section",
                choices=_definition_choices(
                    EMPLOYEES_FILTERS_DEFINITION,
                    "operational_section",
                    (
                        ("all", "الكل"),
                        *Employee.OperationalSection.choices,
                    ),
                ),
            ),
            ACTIVE_FILTER,
        ),
        landscape=True,
        default_filename="employees",
    ),

    "shift_assignments": ExportReportDefinition(
        key="shift_assignments",
        title="سجل تسكين الموظفين",
        module="الورديات",
        description=(
            "تسكين الموظفين على الورديات "
            "وحالة التأكيد."
        ),
        icon="assignments",
        selector_key="shift_assignments",
        columns=SHIFT_ASSIGNMENT_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            SHIFT_FILTER,
            SECTION_FILTER,
            EMPLOYEE_FILTER,
            ExportFilter(
                key="is_confirmed",
                label="حالة التأكيد",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="is_confirmed",
                choices=(
                    ("true", "مؤكد"),
                    ("false", "غير مؤكد"),
                ),
            ),
        ),
        landscape=True,
        default_filename="shift_assignments",
    ),

    "door_distribution": ExportReportDefinition(
        key="door_distribution",
        title="سجل توزيع الأبواب",
        module="التوزيع",
        description=(
            "توزيع الموظفين والمشرفين "
            "على الأبواب والورديات."
        ),
        icon="distribution",
        selector_key="door_distribution",
        columns=DOOR_DISTRIBUTION_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            SHIFT_FILTER,
            SECTION_FILTER,
            EMPLOYEE_FILTER,
            ZONE_FILTER,
            DOOR_DIRECTION_FILTER,
            ACTIVE_FILTER,
        ),
        landscape=True,
        include_indicators=True,
        default_filename="door_distribution",
    ),

    "locations": ExportReportDefinition(
        key="locations",
        title="سجل المواقع والأبواب",
        module="المواقع",
        description=(
            "المناطق والأبواب وحالة "
            "التفعيل وجهات الأبواب."
        ),
        icon="doors",
        selector_key="locations",
        columns=LOCATION_COLUMNS,
        filters=(
            ZONE_FILTER,
            OPERATIONAL_SECTION_FILTER,
            DOOR_DIRECTION_FILTER,
            ACTIVE_FILTER,
        ),
        landscape=False,
        include_indicators=True,
        default_filename="locations_doors",
    ),

    "breaks": ExportReportDefinition(
        key="breaks",
        title="سجل الراحات",
        module="الراحات",
        description=(
            "خطط الراحة والموظفون "
            "والورديات وحالة التفعيل."
        ),
        icon="breaks",
        selector_key="breaks",
        columns=BREAK_COLUMNS,
        filters=(
            SHIFT_FILTER,
            EMPLOYEE_FILTER,
            ACTIVE_FILTER,
        ),
        landscape=True,
        default_filename="breaks",
    ),

    "incidents": ExportReportDefinition(
        key="incidents",
        title="سجل البلاغات التشغيلية",
        module="البلاغات",
        description=(
            "البلاغات والأولويات والحالات "
            "وتواريخ المعالجة."
        ),
        icon="incidents",
        selector_key="incidents",
        columns=INCIDENT_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            SHIFT_FILTER,
            SECTION_FILTER,
            DOOR_DIRECTION_FILTER,
            ExportFilter(
                key="incident_status",
                label="حالة البلاغ",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="status",
            ),
            ExportFilter(
                key="priority",
                label="الأولوية",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="priority",
            ),
        ),
        landscape=True,
        include_indicators=True,
        default_filename="incidents",
    ),

    "maintenance": ExportReportDefinition(
        key="maintenance",
        title="سجل طلبات الصيانة",
        module="الصيانة",
        description=(
            "طلبات الصيانة والأولويات "
            "والحالات ومراحل التنفيذ."
        ),
        icon="maintenance",
        selector_key="maintenance",
        columns=MAINTENANCE_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            SHIFT_FILTER,
            SECTION_FILTER,
            DOOR_DIRECTION_FILTER,
            ExportFilter(
                key="maintenance_status",
                label="حالة الصيانة",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="status",
            ),
            ExportFilter(
                key="priority",
                label="درجة الخطورة",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="priority",
            ),
        ),
        landscape=True,
        include_indicators=True,
        default_filename="maintenance_requests",
    ),

    "reports": ExportReportDefinition(
        key="reports",
        title="سجل التقارير التشغيلية",
        module="التقارير",
        description=(
            "تقارير الورديات والمؤشرات "
            "وحالات الاعتماد."
        ),
        icon="reports",
        selector_key="reports",
        columns=REPORT_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            SHIFT_FILTER,
            SECTION_FILTER,
            ExportFilter(
                key="report_status",
                label="حالة التقرير",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="status",
            ),
            ExportFilter(
                key="report_type",
                label="نوع التقرير",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="report_type",
            ),
        ),
        landscape=True,
        include_indicators=True,
        include_summary=True,
        include_recommendations=True,
        include_approval=True,
        default_filename="shift_reports",
    ),

    "announcements": ExportReportDefinition(
        key="announcements",
        title="سجل التعاميم",
        module="التعاميم",
        description=(
            "التعاميم الإدارية والأولويات "
            "والحالة والمنشئ."
        ),
        icon="announcements",
        selector_key="announcements",
        columns=ANNOUNCEMENT_COLUMNS,
        filters=(
            *DATE_RANGE_FILTERS,
            ExportFilter(
                key="priority",
                label="الأولوية",
                filter_type=FILTER_TYPE_CHOICE,
                parameter="priority",
            ),
            ACTIVE_FILTER,
        ),
        landscape=True,
        default_filename="announcements",
    ),
}


# ==================================================
# الوصول إلى سجل التقارير
# ==================================================

def get_report_definition(
    report_key: str,
) -> ExportReportDefinition:
    """
    إرجاع تعريف تقرير أو رفع KeyError.
    """
    normalized_key = (
        report_key
        or ""
    ).strip().lower()

    if normalized_key not in REPORT_REGISTRY:
        raise KeyError(
            f"نوع التقرير غير مسجل: {report_key}"
        )

    return REPORT_REGISTRY[
        normalized_key
    ]


def get_report_definition_or_none(
    report_key: str,
) -> ExportReportDefinition | None:
    """
    إرجاع تعريف التقرير أو None.
    """
    try:
        return get_report_definition(
            report_key
        )
    except KeyError:
        return None


def get_registered_reports() -> tuple[
    ExportReportDefinition,
    ...
]:
    """
    إرجاع جميع التقارير المسجلة.
    """
    return tuple(
        REPORT_REGISTRY.values()
    )


def get_report_choices() -> tuple[
    tuple[str, str],
    ...
]:
    """
    خيارات أنواع التقارير للنماذج.
    """
    return tuple(
        (
            definition.key,
            definition.title,
        )
        for definition
        in REPORT_REGISTRY.values()
    )


def get_format_choices() -> tuple[
    tuple[str, str],
    ...
]:
    """
    خيارات صيغ التصدير.
    """
    return (
        (FORMAT_EXCEL, "Excel"),
        (FORMAT_PDF, "PDF"),
        (FORMAT_CSV, "CSV"),
    )


def iter_report_columns(
    report_key: str,
    export_format: str,
) -> Iterable[ExportColumn]:
    """
    المرور على أعمدة التقرير الخاصة بالصيغة.
    """
    definition = get_report_definition(
        report_key
    )

    yield from definition.get_columns(
        export_format
    )