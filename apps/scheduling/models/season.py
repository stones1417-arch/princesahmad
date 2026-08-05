from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Season(models.Model):
    class SeasonType(models.TextChoices):
        RAMADAN = "ramadan", "رمضان"
        HAJJ = "hajj", "الحج"
        OTHER = "other", "موسم آخر"

    class SeasonStatus(models.TextChoices):
        DRAFT = "draft", "مسودة"
        ACTIVE = "active", "نشط"
        INACTIVE = "inactive", "معطل"
        ARCHIVED = "archived", "مؤرشف"

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="اسم الموسم",
    )

    season_type = models.CharField(
        max_length=20,
        choices=SeasonType.choices,
        default=SeasonType.OTHER,
        db_index=True,
        verbose_name="نوع الموسم",
    )

    start_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ البداية",
    )

    end_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ النهاية",
    )

    status = models.CharField(
        max_length=20,
        choices=SeasonStatus.choices,
        default=SeasonStatus.DRAFT,
        db_index=True,
        verbose_name="حالة الموسم",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_seasons",
        verbose_name="أنشئ بواسطة",
    )

    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_seasons",
        verbose_name="فُعّل بواسطة",
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_seasons",
        verbose_name="أُرشف بواسطة",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    activated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-start_date"]

        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="season_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()

        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError(
                    {
                        "end_date": (
                            "تاريخ نهاية الموسم يجب أن يكون بعد "
                            "تاريخ البداية أو مساويًا له."
                        )
                    }
                )

            overlapping = (
                Season.objects
                .exclude(pk=self.pk)
                .exclude(status=self.SeasonStatus.ARCHIVED)
                .filter(
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                )
            )

            if overlapping.exists():
                raise ValidationError(
                    "توجد فترة موسم أخرى متداخلة مع الفترة المحددة."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == self.SeasonStatus.ACTIVE

    @property
    def is_ended(self):
        return self.end_date < timezone.localdate()

    def __str__(self):
        return self.name