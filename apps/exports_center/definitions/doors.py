"""تعريف تقرير الأبواب/المواقع مع دعم operational_section."""

from __future__ import annotations

DOORS_COLUMNS_DEFINITION = (
    {
        "key": "door_number",
        "header": "رقم الباب",
    },
    {
        "key": "door_name",
        "header": "اسم الباب",
    },
    {
        "key": "zone",
        "header": "المنطقة",
    },
    {
        "key": "operational_section",
        "header": "القسم التشغيلي",
        "display_method": "get_operational_section_display",
    },
    {
        "key": "direction",
        "header": "جهة الباب",
    },
)

DOORS_FILTERS_DEFINITION = (
    {
        "key": "operational_section",
        "label": "القسم التشغيلي",
        "parameter": "operational_section",
        "choices": (
            ("all", "الكل"),
            ("male", "رجالي"),
            ("female", "نسائي"),
            ("shared", "مشترك"),
        ),
    },
)
