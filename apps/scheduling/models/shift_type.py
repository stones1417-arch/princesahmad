from __future__ import annotations

from django.db import models


class ShiftType(models.Model):
    """
    تعريف نوع الوردية الأساسي، مثل:
    - الفجر
    - الضحى
    - المسائية
    - المساندة
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="اسم الوردية",
    )

    start_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="وقت البداية الافتراضي",
    )

    end_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="وقت النهاية الافتراضي",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشطة",
    )

    ordering = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="الترتيب",
    )

    class Meta:
        ordering = [
            "ordering",
            "name",
        ]

        verbose_name = "نوع وردية"
        verbose_name_plural = "أنواع الورديات"

    def __str__(self) -> str:
        return self.name