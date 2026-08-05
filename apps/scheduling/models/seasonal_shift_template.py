from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class SeasonalShiftTemplate(models.Model):
    """
    قالب وقت وردية مرتبط بموسم محدد.
    """

    season = models.ForeignKey(
        "scheduling.Season",
        on_delete=models.CASCADE,
        related_name="shift_templates",
        verbose_name="الموسم",
    )

    name = models.CharField(
        max_length=100,
        verbose_name="اسم الوردية الموسمية",
    )

    start_time = models.TimeField(
        verbose_name="وقت البداية",
    )

    end_time = models.TimeField(
        verbose_name="وقت النهاية",
    )

    crosses_midnight = models.BooleanField(
        default=False,
        verbose_name="تمتد لليوم التالي",
        help_text=(
            "فعّل هذا الخيار إذا كانت الوردية تبدأ في يوم "
            "وتنتهي بعد منتصف الليل في اليوم التالي."
        ),
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

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = [
            "season",
            "ordering",
            "start_time",
        ]

        verbose_name = "قالب وردية موسمية"
        verbose_name_plural = "قوالب الورديات الموسمية"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "season",
                    "name",
                ],
                name="unique_shift_template_name_per_season",
            ),
            models.UniqueConstraint(
                fields=[
                    "season",
                    "start_time",
                    "end_time",
                ],
                name="unique_shift_template_time_per_season",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "season",
                    "is_active",
                ],
                name="season_template_active_idx",
            ),
            models.Index(
                fields=[
                    "season",
                    "ordering",
                ],
                name="season_template_order_idx",
            ),
        ]

    def clean(self) -> None:
        """
        التحقق من صحة وقت الوردية وحالة الموسم.
        """
        super().clean()

        errors: dict[str, str] = {}

        if self.start_time and self.end_time:
            if self.start_time == self.end_time:
                errors["end_time"] = (
                    "وقت بداية الوردية لا يمكن أن يساوي وقت نهايتها."
                )

            elif (
                not self.crosses_midnight
                and self.end_time < self.start_time
            ):
                errors["end_time"] = (
                    "وقت النهاية يسبق وقت البداية. "
                    "فعّل خيار امتداد الوردية لليوم التالي."
                )

            elif (
                self.crosses_midnight
                and self.end_time > self.start_time
            ):
                errors["crosses_midnight"] = (
                    "وقت النهاية بعد وقت البداية في اليوم نفسه، "
                    "لذلك لا يلزم تفعيل الامتداد لليوم التالي."
                )

        if self.season_id:
            season = self.season

            if season.status == season.SeasonStatus.ARCHIVED:
                errors["season"] = (
                    "لا يمكن إنشاء أو تعديل قالب وردية "
                    "داخل موسم مؤرشف."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        تطبيق قواعد التحقق قبل الحفظ.
        """
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self) -> str:
        season_name = (
            self.season.name
            if self.season_id
            else "بدون موسم"
        )

        return f"{season_name} - {self.name}"