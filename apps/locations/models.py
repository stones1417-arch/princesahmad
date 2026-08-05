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
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    door_number__gte=1,
                    door_number__lte=41,
                ),
                name="door_number_between_1_and_41",
            ),
        ]

    def __str__(self):
        """
        يظهر داخل القوائم المنسدلة بهذا الشكل:
        باب 1، باب 2، ... باب 41.
        """
        return f"باب {self.door_number}"