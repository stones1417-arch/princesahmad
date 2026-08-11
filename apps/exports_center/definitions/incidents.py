"""تعريف تقارير البلاغات مع دعم القسم التشغيلي section."""

from __future__ import annotations

INCIDENTS_COLUMNS_DEFINITION = (
    {
        "key": "section",
        "header": "القسم التشغيلي",
        "section_labels": {
            "male": "رجالي",
            "female": "نسائي",
            "shared": "رجالي ونسائي",
        },
    },
)

INCIDENTS_FILTERS_DEFINITION = (
    {
        "key": "section",
        "label": "القسم التشغيلي",
        "parameter": "section",
        "choices": (
            ("all", "الكل"),
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
    },
)
