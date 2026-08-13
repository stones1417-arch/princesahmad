from __future__ import annotations

import re

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

    @staticmethod
    def get_official_door_direction(door_number: object) -> str:
        return get_official_door_direction(door_number)


OFFICIAL_DOOR_CODES = tuple(
    [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6B",
        "6A",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
    ]
)

OFFICIAL_DOOR_SET = frozenset(OFFICIAL_DOOR_CODES)
OFFICIAL_SORT_ORDER = {
    code: index + 1
    for index, code in enumerate(OFFICIAL_DOOR_CODES)
}

OFFICIAL_MALE_DOOR_CODES = frozenset(
    {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6B",
        "6A",
        "7",
        "8",
        "9",
        "10",
        "11",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
    }
)

OFFICIAL_FEMALE_DOOR_CODES = frozenset(
    {
        "12",
        "13",
        "14",
        "15",
        "16",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
    }
)

LEGACY_SHARED_DOOR_CODES = frozenset({"13", "17", "25", "29", "38"})
LEGACY_SHARED_DOOR_NUMBERS = frozenset({13, 17, 25, 29, 38})


def normalize_door_code(value: object) -> str:
    """Normalizes a door code to the canonical text form used by the official seed."""
    if value is None:
        raise ValidationError("رقم الباب مطلوب.")

    if isinstance(value, int):
        if 1 <= value <= 41:
            return str(value)
        raise ValidationError("رقم الباب خارج نطاق الأبواب المعتمد في المنصة.")

    text = str(value).strip()
    if not text:
        raise ValidationError("رقم الباب مطلوب.")

    normalized = text.replace(" ", "").upper()

    if re.fullmatch(r"[0-9]+", normalized):
        numeric_value = int(normalized)
        if 1 <= numeric_value <= 41:
            return str(numeric_value)
        raise ValidationError("رقم الباب خارج نطاق الأبواب المعتمد في المنصة.")

    if re.fullmatch(r"6[A-B]", normalized):
        return normalized

    raise ValidationError("رقم الباب غير صالح. القيم المعتمدة: 1..41، 6A، 6B")


def get_official_door_direction(door_number: object) -> str:
    """Return the official direction for a door code without guessing on ambiguous legacy values."""
    code = normalize_door_code(door_number)

    if code == "6B":
        return DoorDirection.SOUTH
    if code == "6A":
        return DoorDirection.WEST
    if code == "6":
        raise ValidationError(
            "رقم الباب 6 غير محدد رسميًا؛ استخدم 6A أو 6B فقط."
        )

    numeric_value = int(code)

    if 1 <= numeric_value <= 5:
        return DoorDirection.SOUTH

    if 7 <= numeric_value <= 14:
        return DoorDirection.WEST

    if 15 <= numeric_value <= 27:
        return DoorDirection.NORTH

    if 28 <= numeric_value <= 35:
        return DoorDirection.EAST

    if 36 <= numeric_value <= 41:
        return DoorDirection.SOUTHEAST

    raise ValidationError("رقم الباب خارج نطاق الأبواب المعتمد في المنصة.")


def get_door_sort_order(door_number: object) -> int:
    """Return the official order position used for sorting doors in the correct sequence."""
    code = normalize_door_code(door_number)
    if code not in OFFICIAL_SORT_ORDER:
        raise ValidationError("رقم الباب غير مدعوم في الترتيب الرسمي.")
    return OFFICIAL_SORT_ORDER[code]


def get_official_section_for_door_number(door_number: object) -> str:
    """Return the official section classification for a door code."""
    code = normalize_door_code(door_number)
    if code in OFFICIAL_FEMALE_DOOR_CODES:
        return "female"
    return "male"


def get_door_direction_label(door_number: object) -> str:
    direction = get_official_door_direction(door_number)
    return {
        DoorDirection.SOUTH: "الجهة الجنوبية",
        DoorDirection.WEST: "الجهة الغربية",
        DoorDirection.NORTH: "الجهة الشمالية",
        DoorDirection.EAST: "الشرقية",
        DoorDirection.SOUTHEAST: "الجنوبية الشرقية",
    }.get(direction, "غير محدد")


def door_code_is_valid(value: object) -> bool:
    try:
        normalize_door_code(value)
    except ValidationError:
        return False
    return True


def is_female_door_code(value: object) -> bool:
    try:
        return normalize_door_code(value) in OFFICIAL_FEMALE_DOOR_CODES
    except ValidationError:
        return False


def is_male_door_code(value: object) -> bool:
    try:
        return normalize_door_code(value) in OFFICIAL_MALE_DOOR_CODES
    except ValidationError:
        return False


def get_official_door_codes_for_direction(direction: str) -> frozenset[str]:
    mapping = {
        DoorDirection.SOUTH: frozenset({"1", "2", "3", "4", "5", "6B"}),
        DoorDirection.WEST: frozenset({"6A", "7", "8", "9", "10", "11", "12", "13", "14"}),
        DoorDirection.NORTH: frozenset({str(number) for number in range(15, 28)}),
        DoorDirection.EAST: frozenset({str(number) for number in range(28, 36)}),
        DoorDirection.SOUTHEAST: frozenset({str(number) for number in range(36, 42)}),
    }
    return mapping.get(direction, frozenset())


def normalize_door_number(value: object) -> str:
    return normalize_door_code(value)