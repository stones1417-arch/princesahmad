from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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

    def __str__(self):
        return self.name


class Door(models.Model):
    """
    باب من أبواب المسجد، من الباب رقم 1 إلى الباب رقم 41.
    """

    class OperationalSection(models.TextChoices):
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"
        SHARED = "shared", "رجالي ونسائي"

    FEMALE_RANGE_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset(
        {12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30}
    )
    SHARED_DOOR_NUMBERS: ClassVar[frozenset[int]] = frozenset(
        {13, 17, 25, 29, 38}
    )
    FEMALE_ONLY_DOOR_NUMBERS: ClassVar[frozenset[int]] = (
        FEMALE_RANGE_DOOR_NUMBERS - SHARED_DOOR_NUMBERS
    )

    door_number = models.PositiveSmallIntegerField(
        unique=True,
        db_index=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(41),
        ],
        verbose_name="رقم الباب",
    )

    name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="اسم الباب",
        help_text="حقل اختياري، ولا يظهر داخل القائمة المنسدلة.",
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
        help_text="يتم تحديد القسم تلقائيًا حسب رقم الباب والقواعد التشغيلية.",
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
        ordering = ["door_number"]

        indexes = [
            models.Index(
                fields=["is_active", "door_number"],
                name="door_active_number_idx",
            ),
            models.Index(
                fields=["zone", "door_number"],
                name="door_zone_number_idx",
            ),
            models.Index(
                fields=["operational_section", "is_active"],
                name="door_section_active_idx",
            ),
            models.Index(
                fields=["zone", "operational_section", "door_number"],
                name="door_zone_section_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    door_number__gte=1,
                    door_number__lte=41,
                ),
                name="door_number_between_1_and_41",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    operational_section__in=["male", "female", "shared"],
                ),
                name="door_valid_operational_section",
            ),
        ]

    @classmethod
    def get_section_for_door_number(cls, door_number: int) -> str:
        if door_number in cls.SHARED_DOOR_NUMBERS:
            return cls.OperationalSection.SHARED
        if door_number in cls.FEMALE_ONLY_DOOR_NUMBERS:
            return cls.OperationalSection.FEMALE
        return cls.OperationalSection.MALE

    def clean(self) -> None:
        super().clean()
        if self.door_number:
            self.operational_section = self.get_section_for_door_number(
                self.door_number
            )

    def save(self, *args, **kwargs) -> None:
        self.operational_section = self.get_section_for_door_number(
            self.door_number
        )
        super().save(*args, **kwargs)

    @property
    def supports_male_operations(self) -> bool:
        return self.operational_section in {
            self.OperationalSection.MALE,
            self.OperationalSection.SHARED,
        }

    @property
    def supports_female_operations(self) -> bool:
        return self.operational_section in {
            self.OperationalSection.FEMALE,
            self.OperationalSection.SHARED,
        }

    def __str__(self):
        """
        يظهر داخل القوائم المنسدلة بهذا الشكل:
        باب 1، باب 2، ... باب 41.
        """
        return f"باب {self.door_number}"