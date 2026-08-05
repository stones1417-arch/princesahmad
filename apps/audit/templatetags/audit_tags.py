from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.html import conditional_escape
from django.utils.safestring import SafeData, mark_safe


register = template.Library()


# ==========================================================
# أدوات داخلية
# ==========================================================


def _is_safe_value(value: Any) -> bool:
    """
    التحقق مما إذا كانت القيمة آمنة مسبقًا للعرض داخل القالب.
    """

    return isinstance(value, SafeData)


def _escape_text(value: Any) -> str:
    """
    تحويل القيمة إلى نص آمن للعرض داخل HTML.
    """

    if value is None:
        return "—"

    if _is_safe_value(value):
        return str(value)

    return str(
        conditional_escape(
            str(value)
        )
    )


def _format_datetime_value(
    value: datetime,
) -> str:
    """
    عرض التاريخ والوقت بالتوقيت المحلي.
    """

    current_value = value

    if timezone.is_aware(current_value):
        current_value = timezone.localtime(
            current_value
        )

    return current_value.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _format_date_value(
    value: date,
) -> str:
    """
    عرض التاريخ.
    """

    return value.strftime(
        "%Y-%m-%d"
    )


def _format_time_value(
    value: time,
) -> str:
    """
    عرض الوقت.
    """

    return value.strftime(
        "%H:%M:%S"
    )


def _format_iterable(
    value: list[Any] | tuple[Any, ...] | set[Any],
) -> str:
    """
    عرض القوائم والمجموعات بصيغة عربية واضحة.
    """

    if not value:
        return "—"

    formatted_items = [
        display_value(item)
        for item in value
    ]

    return "، ".join(
        formatted_items
    )


def _format_mapping(
    value: Mapping[Any, Any],
) -> str:
    """
    عرض القاموس بصورة مختصرة وآمنة.
    """

    if not value:
        return "—"

    formatted_items = []

    for key, item in value.items():
        formatted_key = _escape_text(
            key
        )

        formatted_value = display_value(
            item
        )

        formatted_items.append(
            f"{formatted_key}: {formatted_value}"
        )

    return "، ".join(
        formatted_items
    )


# ==========================================================
# فلتر قراءة قيمة من قاموس
# ==========================================================


@register.filter(
    name="get_item",
)
def get_item(
    mapping: Any,
    key: Any,
):
    """
    إرجاع قيمة من قاموس أو كائن شبيه بالقاموس
    باستخدام مفتاح متغير داخل قالب Django.

    الاستخدام:

        {{ type_counts|get_item:audit_type.key }}

    عند عدم وجود المفتاح ترجع None بدل رفع خطأ.
    """

    if mapping is None:
        return None

    if key is None:
        return None

    if isinstance(
        mapping,
        Mapping,
    ):
        return mapping.get(
            key
        )

    getter = getattr(
        mapping,
        "get",
        None,
    )

    if callable(
        getter
    ):
        try:
            return getter(
                key
            )

        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):
            return None

    try:
        return mapping[
            key
        ]

    except (
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
    ):
        return None


# ==========================================================
# فلتر عرض القيمة
# ==========================================================


@register.filter(
    name="display_value",
)
def display_value(
    value: Any,
) -> str:
    """
    تجهيز قيمة سجل التدقيق للعرض بصورة واضحة وآمنة.

    يدعم:
    - None
    - Boolean
    - التاريخ والوقت
    - القوائم والمجموعات
    - القواميس
    - Decimal
    - النصوص العادية
    """

    if value is None:
        return "—"

    if value is True:
        return "نعم"

    if value is False:
        return "لا"

    if isinstance(
        value,
        datetime,
    ):
        return _format_datetime_value(
            value
        )

    if isinstance(
        value,
        date,
    ):
        return _format_date_value(
            value
        )

    if isinstance(
        value,
        time,
    ):
        return _format_time_value(
            value
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
        Mapping,
    ):
        return _format_mapping(
            value
        )

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return _format_iterable(
            value
        )

    text = str(
        value
    ).strip()

    if not text:
        return "—"

    return _escape_text(
        text
    )


# ==========================================================
# فلتر JSON منسق
# ==========================================================


@register.filter(
    name="pretty_json",
)
def pretty_json(
    value: Any,
) -> str:
    """
    تحويل القيمة إلى JSON منسق للعرض داخل <pre>.

    الاستخدام:

        {{ record.old_value|pretty_json }}
    """

    if value in (
        None,
        "",
    ):
        value = {}

    try:
        output = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            cls=DjangoJSONEncoder,
        )

    except (
        TypeError,
        ValueError,
    ):
        output = str(
            value
        )

    return _escape_text(
        output
    )


# ==========================================================
# فلتر مقارنة القيم
# ==========================================================


@register.filter(
    name="values_differ",
)
def values_differ(
    old_value: Any,
    new_value: Any,
) -> bool:
    """
    إرجاع True إذا اختلفت القيمتان.

    الاستخدام:

        {% if old_value|values_differ:new_value %}
    """

    return old_value != new_value


# ==========================================================
# فلتر اسم المستخدم
# ==========================================================


@register.filter(
    name="user_display_name",
)
def user_display_name(
    user: Any,
) -> str:
    """
    إرجاع الاسم الأفضل لعرض المستخدم.
    """

    if user is None:
        return "عملية نظامية"

    get_full_name = getattr(
        user,
        "get_full_name",
        None,
    )

    full_name = ""

    if callable(
        get_full_name
    ):
        full_name = str(
            get_full_name() or ""
        ).strip()

    if full_name:
        return _escape_text(
            full_name
        )

    username = str(
        getattr(
            user,
            "username",
            "",
        )
        or ""
    ).strip()

    if username:
        return _escape_text(
            username
        )

    return "مستخدم النظام"


# ==========================================================
# فلتر الحرف الأول
# ==========================================================


@register.filter(
    name="initial",
)
def initial(
    value: Any,
) -> str:
    """
    إرجاع أول حرف من القيمة للاستخدام في الصورة الرمزية.
    """

    text = str(
        value or ""
    ).strip()

    if not text:
        return "ن"

    return _escape_text(
        text[0]
    )


# ==========================================================
# فلتر نعم / لا
# ==========================================================


@register.filter(
    name="yes_no_ar",
)
def yes_no_ar(
    value: Any,
) -> str:
    """
    تحويل القيمة المنطقية إلى نعم أو لا.
    """

    return (
        "نعم"
        if bool(value)
        else "لا"
    )


# ==========================================================
# فلتر حالة التغيير
# ==========================================================


@register.filter(
    name="change_status_label",
)
def change_status_label(
    changed: Any,
) -> str:
    """
    عرض وصف مختصر لحالة التغيير.
    """

    return (
        "تم التغيير"
        if bool(changed)
        else "دون تغيير"
    )


# ==========================================================
# وسم عرض قيمة HTML
# ==========================================================


@register.simple_tag(
    name="audit_value",
)
def audit_value(
    value: Any,
    css_class: str = "",
) -> str:
    """
    إخراج قيمة داخل عنصر span بصورة آمنة.

    الاستخدام:

        {% audit_value change.old_value "change-value" %}
    """

    safe_class = _escape_text(
        css_class
    )

    safe_value = display_value(
        value
    )

    html = (
        f'<span class="{safe_class}">'
        f"{safe_value}"
        "</span>"
    )

    return mark_safe(
        html
    )