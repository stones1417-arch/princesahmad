"""تعريف تقرير الموظفين (columns + filters) بصيغة معيارية قابلة لإعادة الاستخدام."""

from __future__ import annotations

EMPLOYEES_COLUMNS_DEFINITION = (
    {
        "key": "employee_number",
        "header": "الرقم الوظيفي",
    },
    {
        "key": "full_name",
        "header": "الاسم الكامل",
    },
    {
        "key": "operational_section",
        "header": "القسم التشغيلي",
        "display_method": "get_operational_section_display",
    },
    {
        "key": "job_title",
        "header": "المسمى الوظيفي",
        "display_method": "get_job_title_display",
    },
    {
        "key": "work_status",
        "header": "حالة الموظف",
        "display_method": "get_work_status_display",
    },
    {
        "key": "is_active",
        "header": "نشط في النظام",
    },
)

EMPLOYEES_FILTERS_DEFINITION = (
    {
        "key": "operational_section",
        "label": "القسم التشغيلي",
        "parameter": "operational_section",
        "choices": (
            ("all", "الكل"),
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
    },
)
