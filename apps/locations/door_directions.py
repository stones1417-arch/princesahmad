from __future__ import annotations

from django.core.exceptions import ValidationError


class DoorDirection:
    SOUTH = "south"
    WEST = "west"
    NORTH = "north"
    EAST = "east"
    SOUTHEAST = "southeast"

    CHOICES = (
        (SOUTH, "الجنوبية"),
        (WEST, "الغربية"),
        (NORTH, "الشمالية"),
        (EAST, "الشرقية"),
        (SOUTHEAST, "الجنوبية الشرقية"),
    )


def normalize_door_number(value: object) -> str:
    """
    توحيد رقم الباب قبل تطبيق قواعد الجهات.

    أمثلة:
    6a -> 6A
    6 b -> 6B
    ١٥ -> يجب تمريره بعد تحويل الأرقام في الإدخال إن لزم.
    """
    normalized = str(value or "").strip().upper().replace(" ", "")

    if not normalized:
        raise ValidationError("رقم الباب مطلوب.")

    return normalized


def get_official_door_direction(door_number: object) -> str:
    """
    إرجاع الجهة الرسمية للباب بحسب خريطة منصة أبواب.
    """
    number = normalize_door_number(door_number)

    if number == "6B":
        return DoorDirection.SOUTH

    if number == "6A":
        return DoorDirection.WEST

    try:
        numeric_number = int(number)
    except ValueError as exc:
        raise ValidationError(
            "رقم الباب غير مدعوم ضمن خريطة الجهات الرسمية."
        ) from exc

    if 1 <= numeric_number <= 5:
        return DoorDirection.SOUTH

    if 7 <= numeric_number <= 14:
        return DoorDirection.WEST

    if 15 <= numeric_number <= 27:
        return DoorDirection.NORTH

    if 28 <= numeric_number <= 35:
        return DoorDirection.EAST

    if 36 <= numeric_number <= 41:
        return DoorDirection.SOUTHEAST

    raise ValidationError(
        "رقم الباب خارج نطاق الأبواب المعتمد في المنصة."
    )