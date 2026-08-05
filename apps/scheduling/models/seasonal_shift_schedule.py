from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class SeasonalShiftSchedule(models.Model):
    """
    جدولة موسمية كاملة، مثل:
    - ورديات رمضان
    - ورديات الحج
    """

    class SeasonType(models.TextChoices):
        RAMADAN = "ramadan", "رمضان"
        HAJJ = "hajj", "الحج"

    name = models.CharField(
        max_length=150,
        verbose_name="اسم الجدولة الموسمية",
    )

    season_type = models.CharField(
        max_length=20,
        choices=SeasonType.choices,
        db_index=True,
        verbose_name="نوع الموسم",
    )

    start_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ بداية الموسم",
    )

    end_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ نهاية الموسم",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="جدولة موسمية نشطة",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاريخ آخر تحديث",
    )

    class Meta:
        ordering = [
            "-start_date",
            "-created_at",
        ]

        verbose_name = "جدولة ورديات موسمية"
        verbose_name_plural = "جدولات الورديات الموسمية"

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    end_date__gte=models.F("start_date"),
                ),
                name="seasonal_schedule_end_after_start",
            ),
        ]

        indexes = [
            models.Index(
                fields=["season_type"],
                name="seasonal_schedule_type_idx",
            ),
            models.Index(
                fields=[
                    "start_date",
                    "end_date",
                ],
                name="seasonal_schedule_dates_idx",
            ),
            models.Index(
                fields=["is_active"],
                name="seasonal_schedule_active_idx",
            ),
        ]

        permissions = [
            (
                "can_create_seasonal_schedule",
                "يمكن إنشاء جدولة ورديات موسمية",
            ),
        ]

    def clean(self) -> None:
        super().clean()

        errors: dict[str, str] = {}

        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            errors["end_date"] = (
                "تاريخ نهاية الموسم يجب أن يكون مساويًا "
                "لتاريخ البداية أو بعده."
            )

        if self.start_date and self.end_date:
            overlapping = (
                SeasonalShiftSchedule.objects
                .exclude(pk=self.pk)
                .filter(
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                )
            )

            if overlapping.exists():
                errors["start_date"] = (
                    "توجد جدولة موسمية أخرى متداخلة "
                    "مع الفترة المحددة."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self) -> str:
        return (
            f"{self.name} - "
            f"{self.get_season_type_display()} "
            f"({self.start_date} إلى {self.end_date})"
        )