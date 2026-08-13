from __future__ import annotations

from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from apps.locations.door_directions import (
    OFFICIAL_FEMALE_DOOR_CODES,
    OFFICIAL_MALE_DOOR_CODES,
    OFFICIAL_SORT_ORDER,
    get_door_sort_order,
    normalize_door_code,
)


class Zone(models.Model):
    """
    منطقة أو جهة داخل المسجد.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="اسم المنطقة",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    class Meta:
        verbose_name = "منطقة"
        verbose_name_plural = "المناطق"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Door(models.Model):
    """Official operational door catalog using the platform's text-safe codes such as 6A and 6B."""

    class OperationalSection(
        models.TextChoices
    ):
        MALE = (
            "male",
            "رجالي",
        )

        FEMALE = (
            "female",
            "نسائي",
        )

        SHARED = (
            "shared",
            "رجالي ونسائي",
        )

    FEMALE_DOOR_CODES: ClassVar[frozenset[str]] = OFFICIAL_FEMALE_DOOR_CODES
    MALE_DOOR_CODES: ClassVar[frozenset[str]] = OFFICIAL_MALE_DOOR_CODES
    OFFICIAL_SORT_ORDER: ClassVar[dict[str, int]] = OFFICIAL_SORT_ORDER
    LEGACY_SHARED_DOOR_CODES: ClassVar[frozenset[str]] = frozenset({"13", "17", "25", "29", "38"})
    LEGACY_SHARED_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset({13, 17, 25, 29, 38})
    SHARED_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset()
    FEMALE_RANGE_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset({12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30})
    FEMALE_ONLY_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset({12, 14, 15, 16, 23, 24, 26, 27, 28, 30})

    door_number = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        verbose_name="رقم الباب",
    )

    sort_order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        editable=False,
        verbose_name="ترتيب الباب الرسمي",
    )

    name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="اسم الباب",
        help_text=(
            "حقل اختياري، ولا يظهر داخل "
            "القائمة المنسدلة."
        ),
    )

    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        related_name="doors",
        verbose_name="المنطقة",
    )

    operational_section = models.CharField(
        max_length=10,
        choices=OperationalSection.choices,
        default=OperationalSection.MALE,
        db_index=True,
        editable=False,
        verbose_name="القسم التشغيلي",
        help_text=(
            "يتم تحديد القسم تلقائيًا حسب "
            "رقم الباب والقواعد التشغيلية."
        ),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشط",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    class Meta:
        verbose_name = "باب"
        verbose_name_plural = "الأبواب"
        ordering = [
            "sort_order",
            "door_number",
        ]

        indexes = [
            models.Index(
                fields=[
                    "is_active",
                    "door_number",
                ],
                name="door_active_number_idx",
            ),
            models.Index(
                fields=[
                    "zone",
                    "door_number",
                ],
                name="door_zone_number_idx",
            ),
            models.Index(
                fields=[
                    "operational_section",
                    "is_active",
                ],
                name="door_section_active_idx",
            ),
            models.Index(
                fields=[
                    "zone",
                    "operational_section",
                    "door_number",
                ],
                name="door_zone_section_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    door_number__in=[
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
                    ],
                ),
                name="door_code_in_official_catalog",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    operational_section__in=[
                        "male",
                        "female",
                        "shared",
                    ],
                ),
                name=(
                    "door_valid_operational_"
                    "section"
                ),
            ),
        ]

    # ==================================================
    # تحديد القسم حسب رقم الباب
    # ==================================================

    @classmethod
    def get_section_for_door_number(
        cls,
        door_number: int | str,
    ) -> str:
        """Return the official operational section for a door code."""
        try:
            normalized_code = normalize_door_code(door_number)
        except ValidationError as exc:
            raise ValueError("رقم الباب غير صالح.") from exc

        if normalized_code in cls.FEMALE_DOOR_CODES:
            return cls.OperationalSection.FEMALE

        if normalized_code in cls.MALE_DOOR_CODES:
            return cls.OperationalSection.MALE

        return cls.OperationalSection.MALE

    @classmethod
    def female_accessible_door_numbers(
        cls,
    ) -> tuple[str, ...]:
        """Return the official female-accessible door codes."""
        return tuple(sorted(cls.FEMALE_DOOR_CODES))

    @classmethod
    def male_accessible_door_numbers(
        cls,
    ) -> tuple[str, ...]:
        """Return the official male-accessible door codes."""
        return tuple(sorted(cls.MALE_DOOR_CODES))

    # ==================================================
    # التحقق والحفظ
    # ==================================================

    def clean(self) -> None:
        """Sync the section and sort order with the official door code while preserving legacy shared rows."""
        super().clean()

        if self.door_number:
            normalized_code = normalize_door_code(self.door_number)
            self.door_number = normalized_code
            self.sort_order = get_door_sort_order(normalized_code)

            legacy_shared_row = (
                self.operational_section == self.OperationalSection.SHARED
            )
            self.operational_section = (
                self.OperationalSection.SHARED
                if legacy_shared_row
                else self.get_section_for_door_number(normalized_code)
            )

    def save(
        self,
        *args,
        **kwargs,
    ) -> None:
        """Normalize the door code and keep legacy shared rows compatible with older data."""
        if self.door_number:
            normalized_code = normalize_door_code(self.door_number)
            self.door_number = normalized_code
            self.sort_order = get_door_sort_order(normalized_code)

            legacy_shared_row = (
                self.operational_section == self.OperationalSection.SHARED
            )
            self.operational_section = (
                self.OperationalSection.SHARED
                if legacy_shared_row
                else self.get_section_for_door_number(normalized_code)
            )

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            normalized_update_fields = set(update_fields)
            if "door_number" in normalized_update_fields:
                normalized_update_fields.update({"operational_section", "sort_order"})
            kwargs["update_fields"] = list(normalized_update_fields)

        super().save(*args, **kwargs)

    # ==================================================
    # خصائص مساعدة
    # ==================================================

    @property
    def is_male_only(self) -> bool:
        """
        هل الباب رجالي فقط؟
        """

        return (
            self.operational_section
            == self.OperationalSection.MALE
        )

    @property
    def is_female_only(self) -> bool:
        """
        هل الباب نسائي فقط؟
        """

        return (
            self.operational_section
            == self.OperationalSection.FEMALE
        )

    @property
    def is_shared(self) -> bool:
        """
        هل الباب مشترك بين القسمين؟
        """

        return (
            self.operational_section
            == self.OperationalSection.SHARED
        )

    @property
    def supports_male_operations(
        self,
    ) -> bool:
        """
        هل يسمح الباب بتشغيل القسم الرجالي؟
        """

        return self.operational_section in {
            self.OperationalSection.MALE,
            self.OperationalSection.SHARED,
        }

    @property
    def supports_female_operations(
        self,
    ) -> bool:
        """
        هل يسمح الباب بتشغيل القسم النسائي؟
        """

        return self.operational_section in {
            self.OperationalSection.FEMALE,
            self.OperationalSection.SHARED,
        }

    @property
    def operational_section_label(
        self,
    ) -> str:
        """
        الاسم العربي للقسم التشغيلي.
        """

        return (
            self.get_operational_section_display()
        )

    def __str__(self) -> str:
        return f"باب {self.door_number}"