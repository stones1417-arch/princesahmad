from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Mapping

from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    F,
    OuterRef,
    Q,
    QuerySet,
    Value,
    When,
)
from django.utils import timezone

from apps.breaks.models import Break
from apps.communications.models import Announcement
from apps.distribution.models import DoorAssignment
from apps.hr.models import Employee
from apps.locations.models import Door
from apps.ops.models import (
    Incident,
    MaintenanceRequest,
)
from apps.reporting.models import ShiftReport
from apps.scheduling.models import (
    ShiftAssignment,
)
from apps.roles.services.section_access import (
    filter_assignments_for_user,
    filter_doors_for_user,
    filter_employees_for_user,
    get_allowed_sections,
    has_institutional_scope,
)

from .registry import (
    DOOR_DIRECTION_NUMBERS,
    get_report_definition,
)


# ==================================================
# الأنواع
# ==================================================

FilterMapping = Mapping[str, Any]
SelectorFunction = Callable[
    [FilterMapping],
    QuerySet,
]


SECTION_ALL_VALUES = {
    "",
    "all",
}

SECTION_ALLOWED_VALUES = {
    DoorAssignment.AssignmentSection.MALE,
    DoorAssignment.AssignmentSection.FEMALE,
}


# ==================================================
# دوال عامة لقراءة الفلاتر
# ==================================================

def _filter_value(
    filters: FilterMapping,
    key: str,
    default: str = "",
) -> str:
    """
    قراءة قيمة فلتر وتحويلها إلى نص نظيف.

    تدعم:
    - dict
    - QueryDict
    - cleaned_data
    """
    if not filters:
        return default

    value = filters.get(
        key,
        default,
    )

    if value is None:
        return default

    # ModelChoiceField قد يعيد كائن نموذج.
    if hasattr(value, "pk"):
        return str(value.pk)

    if isinstance(value, bool):
        return (
            "true"
            if value
            else "false"
        )

    return str(value).strip()


def _filter_object(
    filters: FilterMapping,
    key: str,
) -> Any:
    """
    إرجاع القيمة الأصلية دون تحويلها إلى نص.

    مفيدة عند استقبال كائن من ModelChoiceField.
    """
    if not filters:
        return None

    return filters.get(key)


def _normalize_section_filter(
    filters: FilterMapping,
) -> str:
    """
    استخراج فلتر القسم التشغيلي وتطبيعه.

    يدعم المفاتيح:
    - section
    - operational_section

    القيم المدعومة:
    - all (أو فارغ)
    - male
    - female
    """
    section_value = (
        _filter_value(
            filters,
            "section",
        )
        or _filter_value(
            filters,
            "operational_section",
        )
    ).strip().lower()

    if section_value in SECTION_ALL_VALUES:
        return ""

    if section_value in SECTION_ALLOWED_VALUES:
        return section_value

    return ""


def _parse_date(
    value: Any,
) -> date | None:
    """
    تحويل قيمة إلى تاريخ.

    تدعم:
    - date
    - datetime
    - YYYY-MM-DD
    """
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return datetime.strptime(
            str(value).strip(),
            "%Y-%m-%d",
        ).date()

    except (
        TypeError,
        ValueError,
    ):
        return None


def _parse_integer(
    value: Any,
) -> int | None:
    """
    تحويل قيمة إلى رقم صحيح موجب.
    """
    if value is None:
        return None

    if hasattr(value, "pk"):
        value = value.pk

    value_text = str(value).strip()

    if not value_text.isdigit():
        return None

    return int(value_text)


def _parse_boolean(
    value: Any,
) -> bool | None:
    """
    تحويل قيم الفلاتر إلى Boolean.

    القيم المدعومة:
    true / false
    1 / 0
    yes / no
    نعم / لا
    """
    if isinstance(value, bool):
        return value

    normalized_value = (
        str(value or "")
        .strip()
        .lower()
    )

    true_values = {
        "true",
        "1",
        "yes",
        "on",
        "نعم",
        "نشط",
    }

    false_values = {
        "false",
        "0",
        "no",
        "off",
        "لا",
        "غير نشط",
    }

    if normalized_value in true_values:
        return True

    if normalized_value in false_values:
        return False

    return None


# ==================================================
# تطبيق الفترات الزمنية
# ==================================================

def _apply_datetime_range(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str,
) -> QuerySet:
    """
    تطبيق من تاريخ وإلى تاريخ على DateTimeField.
    """
    date_from = _parse_date(
        _filter_object(
            filters,
            "date_from",
        )
    )

    date_to = _parse_date(
        _filter_object(
            filters,
            "date_to",
        )
    )

    if date_from:
        queryset = queryset.filter(
            **{
                f"{field_name}__date__gte": (
                    date_from
                )
            }
        )

    if date_to:
        queryset = queryset.filter(
            **{
                f"{field_name}__date__lte": (
                    date_to
                )
            }
        )

    return queryset


def _apply_date_range(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str,
) -> QuerySet:
    """
    تطبيق من تاريخ وإلى تاريخ على DateField.
    """
    date_from = _parse_date(
        _filter_object(
            filters,
            "date_from",
        )
    )

    date_to = _parse_date(
        _filter_object(
            filters,
            "date_to",
        )
    )

    if date_from:
        queryset = queryset.filter(
            **{
                f"{field_name}__gte": (
                    date_from
                )
            }
        )

    if date_to:
        queryset = queryset.filter(
            **{
                f"{field_name}__lte": (
                    date_to
                )
            }
        )

    return queryset


# ==================================================
# تطبيق فلتر الوردية
# ==================================================

def _apply_shift_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str = "shift_plan_id",
) -> QuerySet:
    """
    تطبيق فلتر الوردية.

    يدعم:
    - shift_plan
    - shift_plan_id
    """
    shift_value = (
        _filter_object(
            filters,
            "shift_plan",
        )
        or _filter_object(
            filters,
            "shift_plan_id",
        )
    )

    shift_plan_id = _parse_integer(
        shift_value
    )

    if shift_plan_id:
        queryset = queryset.filter(
            **{
                field_name: shift_plan_id
            }
        )

    return queryset


# ==================================================
# تطبيق فلتر الموظف
# ==================================================

def _apply_employee_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str = "employee_id",
) -> QuerySet:
    """
    تطبيق فلتر الموظف.

    يدعم:
    - employee
    - employee_id
    """
    employee_value = (
        _filter_object(
            filters,
            "employee",
        )
        or _filter_object(
            filters,
            "employee_id",
        )
    )

    employee_id = _parse_integer(
        employee_value
    )

    if employee_id:
        queryset = queryset.filter(
            **{
                field_name: employee_id
            }
        )

    return queryset


# ==================================================
# تطبيق فلتر المنطقة
# ==================================================

def _apply_zone_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str,
) -> QuerySet:
    """
    تطبيق فلتر المنطقة.
    """
    zone_value = (
        _filter_object(
            filters,
            "zone",
        )
        or _filter_object(
            filters,
            "zone_id",
        )
    )

    zone_id = _parse_integer(
        zone_value
    )

    if zone_id:
        queryset = queryset.filter(
            **{
                field_name: zone_id
            }
        )

    return queryset


def _apply_employee_section_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str,
) -> QuerySet:
    """
    تطبيق فلتر القسم على الحقول المرتبطة بجنس الموظف.
    """
    section_value = _normalize_section_filter(
        filters
    )

    if not section_value:
        return queryset

    return queryset.filter(
        **{
            field_name: section_value,
        }
    )


def _apply_assignment_section_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str = "section",
) -> QuerySet:
    """
    تطبيق فلتر القسم على تسكينات الأبواب.
    """
    section_value = _normalize_section_filter(
        filters
    )

    if not section_value:
        return queryset

    return queryset.filter(
        **{
            field_name: section_value,
        }
    )


def _apply_operational_section_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    field_name: str = "operational_section",
) -> QuerySet:
    """
    تطبيق فلتر القسم التشغيلي للأبواب.
    """
    section_value = _filter_value(
        filters,
        "operational_section",
    ).strip().lower()

    if section_value in SECTION_ALL_VALUES:
        return queryset

    valid_values = {
        Door.OperationalSection.MALE,
        Door.OperationalSection.FEMALE,
        Door.OperationalSection.SHARED,
    }

    if section_value not in valid_values:
        return queryset

    return queryset.filter(
        **{
            field_name: section_value,
        }
    )


def _incident_section_q(
    section_value: str,
) -> Q:
    """
    شرط ربط البلاغ بقسم التسكين الفعلي للباب داخل الوردية.
    """
    return Q(section=section_value) | (
        Q(section="")
        & Q(
            shift_plan__door_assignments__section=(
                section_value
            ),
            shift_plan__door_assignments__is_active=True,
            shift_plan__door_assignments__door__door_number=F(
                "door_shift__door_number"
            ),
        )
    )


def _maintenance_section_q(
    section_value: str,
) -> Q:
    """
    شرط ربط طلب الصيانة بقسم التسكين الفعلي للباب داخل الوردية.
    """
    return Q(section=section_value) | (
        Q(section="")
        & Q(
            door_shift__shift_plan__door_assignments__section=(
                section_value
            ),
            door_shift__shift_plan__door_assignments__is_active=True,
            door_shift__shift_plan__door_assignments__door__door_number=F(
                "door_shift__door_number"
            ),
        )
    )


def _reports_section_q(
    section_value: str,
) -> Q:
    """
    شرط ربط تقرير الوردية بقسم التسكين داخل الوردية نفسها.
    """
    return Q(
        shift_plan__door_assignments__section=(
            section_value
        ),
        shift_plan__door_assignments__is_active=True,
    )


def _annotate_incident_section(
    queryset: QuerySet,
) -> QuerySet:
    """
    إضافة حقل section للبلاغات اعتمادًا على DoorAssignment.section.
    """
    male_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.MALE,
        door__door_number=OuterRef(
            "door_shift__door_number"
        ),
    )

    female_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.FEMALE,
        door__door_number=OuterRef(
            "door_shift__door_number"
        ),
    )

    return (
        queryset
        .annotate(
            _has_male_section=Exists(
                male_exists
            ),
            _has_female_section=Exists(
                female_exists
            ),
        )
        .annotate(
            resolved_section=Case(
                When(
                    _has_male_section=True,
                    _has_female_section=True,
                    then=Value("shared"),
                ),
                When(
                    _has_male_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.MALE
                    ),
                ),
                When(
                    _has_female_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.FEMALE
                    ),
                ),
                default=Value(""),
                output_field=CharField(),
            ),
        )
    )


def _annotate_maintenance_section(
    queryset: QuerySet,
) -> QuerySet:
    """
    إضافة حقل section لطلبات الصيانة اعتمادًا على DoorAssignment.section.
    """
    male_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "door_shift__shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.MALE,
        door__door_number=OuterRef(
            "door_shift__door_number"
        ),
    )

    female_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "door_shift__shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.FEMALE,
        door__door_number=OuterRef(
            "door_shift__door_number"
        ),
    )

    return (
        queryset
        .annotate(
            _has_male_section=Exists(
                male_exists
            ),
            _has_female_section=Exists(
                female_exists
            ),
        )
        .annotate(
            resolved_section=Case(
                When(
                    _has_male_section=True,
                    _has_female_section=True,
                    then=Value("shared"),
                ),
                When(
                    _has_male_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.MALE
                    ),
                ),
                When(
                    _has_female_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.FEMALE
                    ),
                ),
                default=Value(""),
                output_field=CharField(),
            ),
        )
    )


def _annotate_reports_section(
    queryset: QuerySet,
) -> QuerySet:
    """
    إضافة حقل section لتقارير الورديات اعتمادًا على DoorAssignment.section.
    """
    male_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.MALE,
    )

    female_exists = DoorAssignment.objects.filter(
        shift_plan_id=OuterRef(
            "shift_plan_id"
        ),
        is_active=True,
        section=DoorAssignment.AssignmentSection.FEMALE,
    )

    return (
        queryset
        .annotate(
            _has_male_section=Exists(
                male_exists
            ),
            _has_female_section=Exists(
                female_exists
            ),
        )
        .annotate(
            section=Case(
                When(
                    _has_male_section=True,
                    _has_female_section=True,
                    then=Value("shared"),
                ),
                When(
                    _has_male_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.MALE
                    ),
                ),
                When(
                    _has_female_section=True,
                    then=Value(
                        DoorAssignment.AssignmentSection.FEMALE
                    ),
                ),
                default=Value(""),
                output_field=CharField(),
            ),
        )
    )


# ==================================================
# تحديد أرقام الأبواب حسب الجهة
# ==================================================

def get_direction_door_numbers(
    direction_key: str,
) -> tuple[str, ...]:
    """
    إرجاع أرقام الأبواب التابعة لجهة محددة.
    """
    normalized_key = (
        direction_key
        or ""
    ).strip().lower()

    numbers = DOOR_DIRECTION_NUMBERS.get(
        normalized_key,
        set(),
    )

    return tuple(
        sorted(
            numbers,
            key=_door_sort_key,
        )
    )


def _door_sort_key(
    door_number: Any,
) -> tuple[int, str]:
    """
    ترتيب أرقام الأبواب التي قد تحتوي A أو B.
    """
    normalized_number = (
        str(door_number or "")
        .strip()
        .upper()
    )

    numeric_part = "".join(
        character
        for character in normalized_number
        if character.isdigit()
    )

    suffix = "".join(
        character
        for character in normalized_number
        if character.isalpha()
    )

    return (
        int(numeric_part or 0),
        suffix,
    )


def _direction_door_query(
    field_name: str,
    direction_key: str,
) -> Q:
    """
    إنشاء Q للأبواب التابعة للجهة.

    يدعم أرقامًا نصية مثل:
    6A
    6B

    ويدعم رقم الباب الموجود داخل اسم الباب.
    """
    door_numbers = get_direction_door_numbers(
        direction_key
    )

    if not door_numbers:
        return Q()

    query = Q()

    for door_number in door_numbers:
        query |= Q(
            **{
                f"{field_name}__iexact": (
                    door_number
                )
            }
        )

    return query


def _apply_door_direction_filter(
    queryset: QuerySet,
    filters: FilterMapping,
    *,
    number_field: str,
    name_field: str | None = None,
) -> QuerySet:
    """
    تطبيق فلتر جهة الأبواب.

    يحاول أولًا المطابقة على حقل رقم الباب.
    وعند توفير name_field يطابق كذلك اسم الباب.
    """
    direction_key = _filter_value(
        filters,
        "door_direction",
    ).lower()

    if (
        not direction_key
        or direction_key
        not in DOOR_DIRECTION_NUMBERS
    ):
        return queryset

    door_numbers = get_direction_door_numbers(
        direction_key
    )

    direction_query = Q()

    for door_number in door_numbers:
        direction_query |= Q(
            **{
                f"{number_field}__iexact": (
                    door_number
                )
            }
        )

        if name_field:
            direction_query |= Q(
                **{
                    f"{name_field}__iexact": (
                        door_number
                    )
                }
            )

            direction_query |= Q(
                **{
                    f"{name_field}__icontains": (
                        f"باب {door_number}"
                    )
                }
            )

    return queryset.filter(
        direction_query
    )


# ==================================================
# Selector: الموظفون
# ==================================================

def employees_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب سجل الموظفين وتطبيق فلاتر:
    - البحث.
    - المسمى الوظيفي.
    - حالة العمل.
    - حالة التفعيل.
    - الموظف.
    - تاريخ المباشرة.
    """
    queryset = (
        Employee.objects
        .select_related("user")
        .order_by(
            "employee_number"
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                full_name__icontains=(
                    search_query
                )
            )
            | Q(
                employee_number__icontains=(
                    search_query
                )
            )
            | Q(
                national_id__icontains=(
                    search_query
                )
            )
            | Q(
                phone_number__icontains=(
                    search_query
                )
            )
            | Q(
                email__icontains=(
                    search_query
                )
            )
        )

    employee_id = _parse_integer(
        _filter_object(
            filters,
            "employee",
        )
    )

    if employee_id:
        queryset = queryset.filter(
            pk=employee_id
        )

    job_title = _filter_value(
        filters,
        "job_title",
    )

    if job_title:
        queryset = queryset.filter(
            job_title=job_title
        )

    work_status = _filter_value(
        filters,
        "work_status",
    )

    if work_status:
        queryset = queryset.filter(
            work_status=work_status
        )

    operational_section = _normalize_section_filter(
        filters
    )

    if operational_section in dict(Employee.OperationalSection.choices):
        queryset = queryset.filter(
            operational_section=operational_section
        )

    is_active = _parse_boolean(
        _filter_object(
            filters,
            "is_active",
        )
    )

    if is_active is not None:
        queryset = queryset.filter(
            is_active=is_active
        )

    queryset = _apply_date_range(
        queryset,
        filters,
        "hire_date",
    )

    return queryset


# ==================================================
# Selector: تسكين الموظفين
# ==================================================

def shift_assignments_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب تسكين الموظفين على الورديات.

    الفلاتر:
    - الوردية.
    - الموظف.
    - الدور التشغيلي.
    - حالة التأكيد.
    - فترة تاريخ الوردية.
    """
    queryset = (
        ShiftAssignment.objects
        .select_related(
            "shift_plan",
            "shift_plan__shift_type",
            "employee",
            "employee__user",
        )
        .order_by(
            "-shift_plan__date",
            "shift_plan__shift_type__start_time",
            "role",
            "employee__employee_number",
        )
    )

    queryset = _apply_shift_filter(
        queryset,
        filters,
        "shift_plan_id",
    )

    queryset = _apply_employee_filter(
        queryset,
        filters,
        "employee_id",
    )

    operational_section = _filter_value(
        filters,
        "operational_section",
    ) or _filter_value(
        filters,
        "section",
    )

    if operational_section in {
        "male",
        "female",
    }:
        queryset = queryset.filter(
            employee__operational_section=operational_section,
        )

    queryset = _apply_employee_section_filter(
        queryset,
        filters,
        "employee__operational_section",
    )

    role = _filter_value(
        filters,
        "role",
    )

    if role:
        queryset = queryset.filter(
            role=role
        )

    is_confirmed = _parse_boolean(
        _filter_object(
            filters,
            "is_confirmed",
        )
    )

    if is_confirmed is not None:
        queryset = queryset.filter(
            is_confirmed=is_confirmed
        )

    queryset = _apply_date_range(
        queryset,
        filters,
        "shift_plan__date",
    )

    return queryset


# ==================================================
# Selector: توزيع الأبواب
# ==================================================

def door_distribution_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب توزيع الموظفين على الأبواب.

    الفلاتر:
    - الوردية.
    - الموظف.
    - المنطقة.
    - جهة الباب.
    - الدور.
    - حالة التفعيل.
    - فترة تاريخ التوزيع.
    """
    queryset = (
        DoorAssignment.objects
        .select_related(
            "shift_plan",
            "shift_plan__shift_type",
            "door",
            "door__zone",
            "employee",
            "employee__user",
        )
        .order_by(
            "-shift_plan__date",
            "door__sort_order",
            "door__door_number",
            "role",
            "employee__employee_number",
        )
    )

    queryset = _apply_shift_filter(
        queryset,
        filters,
        "shift_plan_id",
    )

    queryset = _apply_employee_filter(
        queryset,
        filters,
        "employee_id",
    )

    queryset = _apply_assignment_section_filter(
        queryset,
        filters,
    )

    queryset = _apply_zone_filter(
        queryset,
        filters,
        "door__zone_id",
    )

    queryset = _apply_door_direction_filter(
        queryset,
        filters,
        number_field="door__door_number",
        name_field="door__name",
    )

    role = _filter_value(
        filters,
        "role",
    )

    if role:
        queryset = queryset.filter(
            role=role
        )

    is_active = _parse_boolean(
        _filter_object(
            filters,
            "is_active",
        )
    )

    if is_active is not None:
        queryset = queryset.filter(
            is_active=is_active
        )

    queryset = _apply_datetime_range(
        queryset,
        filters,
        "assigned_at",
    )

    return queryset


# ==================================================
# Selector: المواقع والأبواب
# ==================================================

def locations_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب المناطق والأبواب.

    الفلاتر:
    - البحث.
    - المنطقة.
    - جهة الأبواب.
    - حالة التفعيل.
    """
    queryset = (
        Door.objects
        .select_related(
            "zone"
        )
        .order_by(
            "sort_order",
            "door_number",
            "name",
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                name__icontains=(
                    search_query
                )
            )
            | Q(
                door_number__icontains=(
                    search_query
                )
            )
            | Q(
                zone__name__icontains=(
                    search_query
                )
            )
        )

    queryset = _apply_zone_filter(
        queryset,
        filters,
        "zone_id",
    )

    queryset = _apply_operational_section_filter(
        queryset,
        filters,
        "operational_section",
    )

    queryset = _apply_door_direction_filter(
        queryset,
        filters,
        number_field="door_number",
        name_field="name",
    )

    is_active = _parse_boolean(
        _filter_object(
            filters,
            "is_active",
        )
    )

    if is_active is not None:
        queryset = queryset.filter(
            is_active=is_active
        )

    return queryset


# ==================================================
# Selector: الراحات
# ==================================================

def breaks_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب خطط الراحات.

    الفلاتر:
    - الموظف.
    - نوع الوردية.
    - حالة التفعيل.
    - أيام الراحة.
    """
    queryset = (
        Break.objects
        .select_related(
            "employee",
            "employee__user",
            "shift_type",
        )
        .order_by(
            "shift_type__start_time",
            "rest_days",
            "employee__employee_number",
        )
    )

    queryset = _apply_employee_filter(
        queryset,
        filters,
        "employee_id",
    )

    shift_type_value = (
        _filter_object(
            filters,
            "shift_type",
        )
        or _filter_object(
            filters,
            "shift_type_id",
        )
    )

    shift_type_id = _parse_integer(
        shift_type_value
    )

    if shift_type_id:
        queryset = queryset.filter(
            shift_type_id=shift_type_id
        )

    rest_days = _filter_value(
        filters,
        "rest_days",
    )

    if rest_days:
        queryset = queryset.filter(
            rest_days=rest_days
        )

    is_active = _parse_boolean(
        _filter_object(
            filters,
            "is_active",
        )
    )

    if is_active is not None:
        queryset = queryset.filter(
            is_active=is_active
        )

    return queryset


# ==================================================
# Selector: البلاغات التشغيلية
# ==================================================

def incidents_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب البلاغات التشغيلية.

    الفلاتر:
    - البحث.
    - الوردية.
    - حالة البلاغ.
    - الأولوية.
    - نوع البلاغ.
    - جهة الباب.
    - فترة الإنشاء.
    """
    queryset = (
        Incident.objects
        .select_related(
            "shift_plan",
            "shift_plan__shift_type",
            "door_shift",
            "created_by",
            "closed_by",
        )
        .order_by(
            "-created_at"
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                incident_number__icontains=(
                    search_query
                )
            )
            | Q(
                description__icontains=(
                    search_query
                )
            )
            | Q(
                reported_by_name__icontains=(
                    search_query
                )
            )
            | Q(
                assigned_to_name__icontains=(
                    search_query
                )
            )
        )

    queryset = _apply_shift_filter(
        queryset,
        filters,
        "shift_plan_id",
    )

    section_value = _normalize_section_filter(
        filters
    )

    if section_value:
        queryset = queryset.filter(
            _incident_section_q(
                section_value
            )
        ).distinct()

    status = (
        _filter_value(
            filters,
            "incident_status",
        )
        or _filter_value(
            filters,
            "status",
        )
    )

    if status:
        queryset = queryset.filter(
            status=status
        )

    priority = _filter_value(
        filters,
        "priority",
    )

    if priority:
        queryset = queryset.filter(
            priority=priority
        )

    incident_type = _filter_value(
        filters,
        "incident_type",
    )

    if incident_type:
        queryset = queryset.filter(
            incident_type=incident_type
        )

    queryset = _apply_door_direction_filter(
        queryset,
        filters,
        number_field="door_shift__door_number",
    )

    queryset = _apply_datetime_range(
        queryset,
        filters,
        "created_at",
    )

    queryset = _annotate_incident_section(
        queryset
    )

    return queryset


# ==================================================
# Selector: طلبات الصيانة
# ==================================================

def maintenance_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب طلبات الصيانة.

    الفلاتر:
    - البحث.
    - الوردية.
    - الحالة.
    - الأولوية.
    - الفني.
    - جهة الباب.
    - فترة الإنشاء.
    """
    queryset = (
        MaintenanceRequest.objects
        .select_related(
            "door_shift",
            "door_shift__shift_plan",
            "door_shift__shift_plan__shift_type",
            "technician",
            "created_by",
        )
        .order_by(
            "-created_at"
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                request_number__icontains=(
                    search_query
                )
            )
            | Q(
                description__icontains=(
                    search_query
                )
            )
            | Q(
                technician_name__icontains=(
                    search_query
                )
            )
        )

    queryset = _apply_shift_filter(
        queryset,
        filters,
        "door_shift__shift_plan_id",
    )

    section_value = _normalize_section_filter(
        filters
    )

    if section_value:
        queryset = queryset.filter(
            _maintenance_section_q(
                section_value
            )
        ).distinct()

    status = (
        _filter_value(
            filters,
            "maintenance_status",
        )
        or _filter_value(
            filters,
            "status",
        )
    )

    if status:
        queryset = queryset.filter(
            status=status
        )

    priority = _filter_value(
        filters,
        "priority",
    )

    if priority:
        queryset = queryset.filter(
            priority=priority
        )

    technician_value = (
        _filter_object(
            filters,
            "technician",
        )
        or _filter_object(
            filters,
            "technician_id",
        )
    )

    technician_id = _parse_integer(
        technician_value
    )

    if technician_id:
        queryset = queryset.filter(
            technician_id=technician_id
        )

    queryset = _apply_door_direction_filter(
        queryset,
        filters,
        number_field="door_shift__door_number",
    )

    queryset = _apply_datetime_range(
        queryset,
        filters,
        "created_at",
    )

    queryset = _annotate_maintenance_section(
        queryset
    )

    return queryset


# ==================================================
# Selector: التقارير التشغيلية
# ==================================================

def reports_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب التقارير التشغيلية.

    الفلاتر:
    - البحث.
    - الوردية.
    - حالة التقرير.
    - نوع التقرير.
    - فترة تاريخ الإنشاء.
    """
    queryset = (
        ShiftReport.objects
        .select_related(
            "shift_plan",
            "shift_plan__shift_type",
            "created_by",
            "approved_by",
        )
        .order_by(
            "-created_at"
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                report_number__icontains=(
                    search_query
                )
            )
            | Q(
                summary__icontains=(
                    search_query
                )
            )
            | Q(
                recommendations__icontains=(
                    search_query
                )
            )
        )

    queryset = _apply_shift_filter(
        queryset,
        filters,
        "shift_plan_id",
    )

    section_value = _normalize_section_filter(
        filters
    )

    if section_value:
        queryset = queryset.filter(
            _reports_section_q(
                section_value
            )
        ).distinct()

    status = (
        _filter_value(
            filters,
            "report_status",
        )
        or _filter_value(
            filters,
            "status",
        )
    )

    if status:
        queryset = queryset.filter(
            status=status
        )

    report_type = _filter_value(
        filters,
        "report_type",
    )

    if report_type:
        queryset = queryset.filter(
            report_type=report_type
        )

    queryset = _apply_datetime_range(
        queryset,
        filters,
        "created_at",
    )

    queryset = _annotate_reports_section(
        queryset
    )

    return queryset


# ==================================================
# Selector: التعاميم
# ==================================================

def announcements_selector(
    filters: FilterMapping,
) -> QuerySet:
    """
    جلب التعاميم الإدارية.

    الفلاتر:
    - البحث.
    - الأولوية.
    - حالة التفعيل.
    - فترة الإنشاء.
    """
    queryset = (
        Announcement.objects
        .select_related(
            "created_by"
        )
        .order_by(
            "-created_at"
        )
    )

    search_query = (
        _filter_value(
            filters,
            "q",
        )
        or _filter_value(
            filters,
            "search",
        )
    )

    if search_query:
        queryset = queryset.filter(
            Q(
                title__icontains=(
                    search_query
                )
            )
            | Q(
                content__icontains=(
                    search_query
                )
            )
        )

    priority = _filter_value(
        filters,
        "priority",
    )

    if priority:
        queryset = queryset.filter(
            priority=priority
        )

    is_active = _parse_boolean(
        _filter_object(
            filters,
            "is_active",
        )
    )

    if is_active is not None:
        queryset = queryset.filter(
            is_active=is_active
        )

    queryset = _apply_datetime_range(
        queryset,
        filters,
        "created_at",
    )

    return queryset


# ==================================================
# سجل المحددات
# ==================================================

SELECTOR_REGISTRY: dict[
    str,
    SelectorFunction,
] = {
    "employees": employees_selector,
    "shift_assignments": (
        shift_assignments_selector
    ),
    "door_distribution": (
        door_distribution_selector
    ),
    "locations": locations_selector,
    "breaks": breaks_selector,
    "incidents": incidents_selector,
    "maintenance": maintenance_selector,
    "reports": reports_selector,
    "announcements": (
        announcements_selector
    ),
}


# ==================================================
# جلب المحدد
# ==================================================

def get_selector(
    selector_key: str,
) -> SelectorFunction:
    """
    إرجاع دالة Selector مسجلة.
    """
    normalized_key = (
        selector_key
        or ""
    ).strip().lower()

    if normalized_key not in SELECTOR_REGISTRY:
        raise KeyError(
            f"محدد البيانات غير مسجل: "
            f"{selector_key}"
        )

    return SELECTOR_REGISTRY[
        normalized_key
    ]


def get_selector_or_none(
    selector_key: str,
) -> SelectorFunction | None:
    """
    إرجاع المحدد أو None.
    """
    try:
        return get_selector(
            selector_key
        )

    except KeyError:
        return None


# ==================================================
# تنفيذ محدد تقرير
# ==================================================

def select_report_queryset(
    report_key: str,
    filters: FilterMapping | None = None,
    user=None,
) -> QuerySet:
    """
    جلب QuerySet لتقرير مسجل في registry.py.

    التسلسل:
    report_key
        -> تعريف التقرير
        -> selector_key
        -> selector
        -> QuerySet
    """
    report_definition = (
        get_report_definition(
            report_key
        )
    )

    selector = get_selector(
        report_definition.selector_key
    )

    queryset = selector(
        filters or {}
    )

    return _apply_user_operational_scope(
        queryset=queryset,
        report_key=report_key,
        user=user,
    )


def _apply_user_operational_scope(
    *,
    queryset: QuerySet,
    report_key: str,
    user,
) -> QuerySet:
    """Apply the active institutional role scope to report data."""
    if not has_institutional_scope(user):
        return queryset

    allowed_sections = get_allowed_sections(user)

    normalized_report_key = str(
        report_key or ""
    ).strip().lower()

    if normalized_report_key == "employees":
        return filter_employees_for_user(
            queryset,
            user,
        )

    if normalized_report_key == "shift_assignments":
        return queryset.filter(
            employee__operational_section__in=allowed_sections,
        )

    if normalized_report_key == "breaks":
        return queryset.filter(
            employee__operational_section__in=allowed_sections,
        )

    if normalized_report_key == "door_distribution":
        return filter_assignments_for_user(
            queryset,
            user,
        )

    if normalized_report_key == "locations":
        return filter_doors_for_user(
            queryset,
            user,
        )

    if normalized_report_key in {
        "incidents",
        "maintenance",
        "reports",
    }:
        return queryset.filter(
            Q(section__in=allowed_sections)
            | Q(section="shared")
        )

    return queryset


# ==================================================
# حساب مؤشرات التقرير
# ==================================================

def build_report_indicators(
    report_key: str,
    queryset: QuerySet,
) -> dict[str, Any]:
    """
    إنشاء مؤشرات مختصرة للتقرير.

    تستخدم في:
    - المعاينة.
    - ورقة المؤشرات في Excel.
    - رأس تقرير PDF.
    """
    normalized_key = (
        report_key
        or ""
    ).strip().lower()

    indicators: dict[str, Any] = {
        "records_count": (
            queryset.count()
        ),
        "generated_at": (
            timezone.localtime()
        ),
    }

    if normalized_key == "employees":
        indicators.update(
            {
                "active_count": (
                    queryset.filter(
                        is_active=True
                    ).count()
                ),
                "inactive_count": (
                    queryset.filter(
                        is_active=False
                    ).count()
                ),
                "male_count": (
                    queryset.filter(
                        operational_section=Employee.OperationalSection.MALE
                    ).count()
                ),
                "female_count": (
                    queryset.filter(
                        operational_section=Employee.OperationalSection.FEMALE
                    ).count()
                ),
            }
        )

    elif normalized_key == "shift_assignments":
        indicators.update(
            {
                "confirmed_count": (
                    queryset.filter(
                        is_confirmed=True
                    ).count()
                ),
                "unconfirmed_count": (
                    queryset.filter(
                        is_confirmed=False
                    ).count()
                ),
                "male_count": (
                    queryset.filter(
                        employee__operational_section=Employee.OperationalSection.MALE
                    ).count()
                ),
                "female_count": (
                    queryset.filter(
                        employee__operational_section=Employee.OperationalSection.FEMALE
                    ).count()
                ),
            }
        )

    elif normalized_key == "door_distribution":
        indicators.update(
            {
                "employees_count": (
                    queryset.values(
                        "employee_id"
                    )
                    .distinct()
                    .count()
                ),
                "doors_count": (
                    queryset.values(
                        "door_id"
                    )
                    .distinct()
                    .count()
                ),
                "shifts_count": (
                    queryset.values(
                        "shift_plan_id"
                    )
                    .distinct()
                    .count()
                ),
                "male_assignments_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.MALE
                    ).count()
                ),
                "female_assignments_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.FEMALE
                    ).count()
                ),
                "male_employees_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.MALE
                    )
                    .values("employee_id")
                    .distinct()
                    .count()
                ),
                "female_employees_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.FEMALE
                    )
                    .values("employee_id")
                    .distinct()
                    .count()
                ),
                "male_doors_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.MALE
                    )
                    .values("door_id")
                    .distinct()
                    .count()
                ),
                "female_doors_count": (
                    queryset.filter(
                        section=DoorAssignment.AssignmentSection.FEMALE
                    )
                    .values("door_id")
                    .distinct()
                    .count()
                ),
            }
        )

    elif normalized_key == "locations":
        indicators.update(
            {
                "active_doors": (
                    queryset.filter(
                        is_active=True
                    ).count()
                ),
                "inactive_doors": (
                    queryset.filter(
                        is_active=False
                    ).count()
                ),
                "zones_count": (
                    queryset.values(
                        "zone_id"
                    )
                    .distinct()
                    .count()
                ),
            }
        )

    elif normalized_key == "breaks":
        indicators.update(
            {
                "active_count": (
                    queryset.filter(
                        is_active=True
                    ).count()
                ),
                "employees_count": (
                    queryset.values(
                        "employee_id"
                    )
                    .distinct()
                    .count()
                ),
            }
        )

    elif normalized_key == "incidents":
        male_incident_count = queryset.filter(
            _incident_section_q(
                DoorAssignment.AssignmentSection.MALE
            )
        ).distinct().count()

        female_incident_count = queryset.filter(
            _incident_section_q(
                DoorAssignment.AssignmentSection.FEMALE
            )
        ).distinct().count()

        indicators.update(
            {
                "status_totals": list(
                    queryset.values(
                        "status"
                    )
                    .annotate(
                        total=Count("id")
                    )
                    .order_by("status")
                ),
                "priority_totals": list(
                    queryset.values(
                        "priority"
                    )
                    .annotate(
                        total=Count("id")
                    )
                    .order_by("priority")
                ),
                "male_count": male_incident_count,
                "female_count": female_incident_count,
            }
        )

    elif normalized_key == "maintenance":
        male_maintenance_count = queryset.filter(
            _maintenance_section_q(
                DoorAssignment.AssignmentSection.MALE
            )
        ).distinct().count()

        female_maintenance_count = queryset.filter(
            _maintenance_section_q(
                DoorAssignment.AssignmentSection.FEMALE
            )
        ).distinct().count()

        indicators.update(
            {
                "status_totals": list(
                    queryset.values(
                        "status"
                    )
                    .annotate(
                        total=Count("id")
                    )
                    .order_by("status")
                ),
                "priority_totals": list(
                    queryset.values(
                        "priority"
                    )
                    .annotate(
                        total=Count("id")
                    )
                    .order_by("priority")
                ),
                "male_count": male_maintenance_count,
                "female_count": female_maintenance_count,
            }
        )

    elif normalized_key == "reports":
        male_report_count = queryset.filter(
            _reports_section_q(
                DoorAssignment.AssignmentSection.MALE
            )
        ).distinct().count()

        female_report_count = queryset.filter(
            _reports_section_q(
                DoorAssignment.AssignmentSection.FEMALE
            )
        ).distinct().count()

        indicators.update(
            {
                "status_totals": list(
                    queryset.values(
                        "status"
                    )
                    .annotate(
                        total=Count("id")
                    )
                    .order_by("status")
                ),
                "total_doors": sum(
                    getattr(
                        report,
                        "total_doors",
                        0,
                    )
                    or 0
                    for report in queryset
                ),
                "open_doors": sum(
                    getattr(
                        report,
                        "open_doors",
                        0,
                    )
                    or 0
                    for report in queryset
                ),
                "maintenance_requests": sum(
                    getattr(
                        report,
                        "total_maintenance_requests",
                        0,
                    )
                    or 0
                    for report in queryset
                ),
                "male_count": male_report_count,
                "female_count": female_report_count,
            }
        )

    elif normalized_key == "announcements":
        indicators.update(
            {
                "active_count": (
                    queryset.filter(
                        is_active=True
                    ).count()
                ),
                "inactive_count": (
                    queryset.filter(
                        is_active=False
                    ).count()
                ),
            }
        )

    return indicators


# ==================================================
# بيانات المعاينة
# ==================================================

def build_report_preview(
    report_key: str,
    filters: FilterMapping | None = None,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """
    تجهيز بيانات المعاينة قبل التصدير.
    """
    report_definition = (
        get_report_definition(
            report_key
        )
    )

    queryset = select_report_queryset(
        report_key,
        filters or {},
    )

    safe_limit = max(
        min(
            int(limit or 50),
            200,
        ),
        1,
    )

    preview_records = list(
        queryset[:safe_limit]
    )

    return {
        "report": report_definition,
        "queryset": queryset,
        "records": preview_records,
        "records_count": queryset.count(),
        "preview_count": len(
            preview_records
        ),
        "indicators": (
            build_report_indicators(
                report_key,
                queryset,
            )
        ),
        "filters": dict(
            filters or {}
        ),
    }
