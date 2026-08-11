"""تعريف تقارير التسكين/التقارير التشغيلية مع دعم section."""

from __future__ import annotations

REPORTS_COLUMNS_DEFINITION = (
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

REPORTS_FILTERS_DEFINITION = (
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
