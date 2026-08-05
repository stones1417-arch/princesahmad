from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ShiftPlan(models.Model):
    """
    خطة وردية تشغيلية يومية أو موسمية.

    القواعد الأساسية:
    - تاريخ الوردية الموسمية يجب أن يكون داخل فترة الموسم.
    - قالب الوردية الموسمية يجب أن يتبع الموسم المحدد.
    - لا يمكن تعديل وردية تابعة لموسم مؤرشف.
    - لا يسمح بتساوي وقت البداية والنهاية.
    - منع تداخل الورديات في التاريخ والفترة نفسها.
    - لا يمكن اعتبار الوردية نشطة ومنتهية في الوقت نفسه.
    """

    class ShiftCategory(models.TextChoices):
        DAILY = "daily", "يومية"
        SEASONAL = "seasonal", "موسمية"

    shift_type = models.ForeignKey(
        "scheduling.ShiftType",
        on_delete=models.PROTECT,
        related_name="shift_plans",
        verbose_name="نوع الوردية",
    )

    category = models.CharField(
        max_length=20,
        choices=ShiftCategory.choices,
        default=ShiftCategory.DAILY,
        db_index=True,
        verbose_name="تصنيف الوردية",
    )

    date = models.DateField(
        db_index=True,
        verbose_name="تاريخ الوردية",
    )

    start_time = models.TimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت البداية",
    )

    end_time = models.TimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت النهاية",
    )

    crosses_midnight = models.BooleanField(
        default=False,
        verbose_name="تمتد لليوم التالي",
        help_text=(
            "فعّل هذا الخيار عندما تبدأ الوردية في يوم "
            "وتنتهي بعد منتصف الليل في اليوم التالي."
        ),
    )

    season = models.ForeignKey(
        "scheduling.Season",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shift_plans",
        verbose_name="الموسم",
    )

    seasonal_template = models.ForeignKey(
        "scheduling.SeasonalShiftTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="generated_shift_plans",
        verbose_name="قالب الوردية الموسمية",
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="الوردية نشطة",
    )

    is_finished = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="الوردية منتهية",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_shift_plans",
        verbose_name="أنشئت بواسطة",
    )

    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_shift_plans",
        verbose_name="فُعّلت بواسطة",
    )

    finished_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finished_shift_plans",
        verbose_name="أُنهيت بواسطة",
    )

    activated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت التفعيل",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت الإنهاء",
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
            "-date",
            "start_time",
            "shift_type",
        ]

        verbose_name = "خطة وردية"
        verbose_name_plural = "خطط الورديات"

        constraints = [
            models.CheckConstraint(
                condition=~Q(
                    is_active=True,
                    is_finished=True,
                ),
                name="shift_not_active_and_finished",
            ),
            models.UniqueConstraint(
                fields=[
                    "date",
                    "shift_type",
                    "season",
                    "seasonal_template",
                ],
                name="unique_shift_plan_definition",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "date",
                    "is_active",
                ],
                name="shift_date_active_idx",
            ),
            models.Index(
                fields=[
                    "season",
                    "date",
                ],
                name="shift_season_date_idx",
            ),
            models.Index(
                fields=[
                    "category",
                    "date",
                ],
                name="shift_category_date_idx",
            ),
        ]

    def clean(self) -> None:
        """
        تطبيق جميع قواعد التحقق الخاصة بخطة الوردية.
        """
        super().clean()

        errors: dict[str, str] = {}

        self._validate_required_times(errors)
        self._validate_time_range(errors)
        self._validate_status(errors)
        self._validate_season(errors)
        self._validate_template(errors)
        self._validate_overlap(errors)

        if errors:
            raise ValidationError(errors)

    def _validate_required_times(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        السماح لقاعدة البيانات القديمة بالقيم الفارغة،
        مع منع إنشاء وردية تشغيلية جديدة دون أوقات.

        يتم تجاوز هذا الشرط فقط عند التعامل مع سجل قديم
        لم تُستكمل بياناته بعد.
        """
        if self.start_time and not self.end_time:
            errors["end_time"] = (
                "يجب تحديد وقت نهاية الوردية."
            )

        if self.end_time and not self.start_time:
            errors["start_time"] = (
                "يجب تحديد وقت بداية الوردية."
            )

    def _validate_time_range(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التحقق من صحة وقت بداية الوردية ونهايتها.
        """
        if not self.start_time or not self.end_time:
            return

        if self.start_time == self.end_time:
            errors["end_time"] = (
                "وقت بداية الوردية لا يمكن أن يساوي وقت نهايتها."
            )
            return

        if (
            not self.crosses_midnight
            and self.end_time < self.start_time
        ):
            errors["end_time"] = (
                "وقت النهاية يسبق وقت البداية. "
                "فعّل خيار امتداد الوردية لليوم التالي."
            )

        if (
            self.crosses_midnight
            and self.end_time > self.start_time
        ):
            errors["crosses_midnight"] = (
                "لا يلزم تفعيل امتداد الوردية لليوم التالي، "
                "لأن وقت النهاية بعد وقت البداية."
            )

    def _validate_status(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التحقق من حالة الوردية ومواعيد التفعيل والإنهاء.
        """
        if self.is_active and self.is_finished:
            errors["is_active"] = (
                "لا يمكن أن تكون الوردية نشطة "
                "ومنتهية في الوقت نفسه."
            )

        if self.is_finished:
            if not self.finished_at:
                self.finished_at = timezone.now()

            self.is_active = False

        elif self.finished_at:
            self.finished_at = None
            self.finished_by = None

        if self.is_active:
            if not self.activated_at:
                self.activated_at = timezone.now()

        elif self.activated_at and not self.is_finished:
            self.activated_at = None
            self.activated_by = None

    def _validate_season(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التحقق من ارتباط الوردية بالموسم.
        """
        if self.category == self.ShiftCategory.SEASONAL:
            if not self.season_id:
                errors["season"] = (
                    "يجب تحديد الموسم للوردية الموسمية."
                )

            if not self.seasonal_template_id:
                errors["seasonal_template"] = (
                    "يجب تحديد قالب الوردية الموسمية."
                )

        if self.category == self.ShiftCategory.DAILY:
            if self.season_id or self.seasonal_template_id:
                errors["category"] = (
                    "الوردية المرتبطة بموسم يجب "
                    "أن يكون تصنيفها موسميًا."
                )

        if not self.season_id:
            return

        season = self.season

        if self.date and not (
            season.start_date
            <= self.date
            <= season.end_date
        ):
            errors["date"] = (
                "تاريخ الوردية يجب أن يكون داخل فترة الموسم "
                f"من {season.start_date} إلى {season.end_date}."
            )

        season_status = getattr(
            season,
            "status",
            None,
        )

        archived_status = getattr(
            getattr(
                season,
                "SeasonStatus",
                None,
            ),
            "ARCHIVED",
            "archived",
        )

        if season_status == archived_status:
            errors["season"] = (
                "لا يمكن إنشاء أو تعديل وردية "
                "داخل موسم مؤرشف."
            )

    def _validate_template(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التحقق من أن القالب الموسمي يتبع الموسم المحدد،
        وأن أوقات الوردية مطابقة للقالب.
        """
        if not self.seasonal_template_id:
            return

        template = self.seasonal_template

        if not self.season_id:
            errors["season"] = (
                "يجب تحديد الموسم عند اختيار "
                "قالب وردية موسمية."
            )
            return

        if template.season_id != self.season_id:
            errors["seasonal_template"] = (
                "قالب الوردية المحدد لا يتبع الموسم المختار."
            )

        if not template.is_active:
            errors["seasonal_template"] = (
                "لا يمكن استخدام قالب وردية موسمية غير نشط."
            )

        if (
            self.start_time
            and self.start_time != template.start_time
        ):
            errors["start_time"] = (
                "وقت بداية الوردية لا يطابق "
                "وقت القالب الموسمي."
            )

        if (
            self.end_time
            and self.end_time != template.end_time
        ):
            errors["end_time"] = (
                "وقت نهاية الوردية لا يطابق "
                "وقت القالب الموسمي."
            )

        if (
            self.crosses_midnight
            != template.crosses_midnight
        ):
            errors["crosses_midnight"] = (
                "خيار امتداد الوردية لا يطابق "
                "القالب الموسمي."
            )

    def _validate_overlap(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        منع تداخل الورديات مع أي وردية أخرى.
        """
        if (
            not self.date
            or not self.start_time
            or not self.end_time
        ):
            return

        datetime_range = self.get_datetime_range()

        if datetime_range is None:
            return

        candidate_start, candidate_end = datetime_range

        possible_shifts = (
            ShiftPlan.objects
            .exclude(pk=self.pk)
            .filter(
                date__range=[
                    self.date - timedelta(days=1),
                    self.date + timedelta(days=1),
                ],
                start_time__isnull=False,
                end_time__isnull=False,
            )
            .select_related("shift_type")
        )

        for other_shift in possible_shifts:
            other_range = (
                other_shift.get_datetime_range()
            )

            if other_range is None:
                continue

            other_start, other_end = other_range

            if (
                candidate_start < other_end
                and candidate_end > other_start
            ):
                errors["start_time"] = (
                    "توجد وردية أخرى متداخلة "
                    "مع الفترة المحددة: "
                    f"{other_shift}."
                )
                break

    def get_datetime_range(
        self,
    ) -> tuple[datetime, datetime] | None:
        """
        إرجاع بداية الوردية ونهايتها كتاريخ ووقت كاملين.

        تعيد None عندما تكون بيانات الوقت غير مكتملة.
        """
        if (
            not self.date
            or not self.start_time
            or not self.end_time
        ):
            return None

        start_datetime = datetime.combine(
            self.date,
            self.start_time,
        )

        end_date = (
            self.date + timedelta(days=1)
            if self.crosses_midnight
            else self.date
        )

        end_datetime = datetime.combine(
            end_date,
            self.end_time,
        )

        return start_datetime, end_datetime

    def save(self, *args, **kwargs):
        """
        تطبيق قواعد التحقق قبل الحفظ.
        """
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def delete(self, *args, **kwargs):
        """
        منع حذف وردية مرتبطة بتوزيعات أو تسكين أو تقرير.
        """
        door_assignments = getattr(
            self,
            "door_assignments",
            None,
        )

        if (
            door_assignments is not None
            and door_assignments.exists()
        ):
            raise ValidationError(
                "لا يمكن حذف وردية لها توزيعات أبواب."
            )

        assignments = getattr(
            self,
            "assignments",
            None,
        )

        if (
            assignments is not None
            and assignments.exists()
        ):
            raise ValidationError(
                "لا يمكن حذف وردية لها تسكين موظفين."
            )

        legacy_assignments = getattr(
            self,
            "shift_assignments",
            None,
        )

        if (
            legacy_assignments is not None
            and legacy_assignments.exists()
        ):
            raise ValidationError(
                "لا يمكن حذف وردية لها تسكين موظفين."
            )

        try:
            report = self.report
        except (
            AttributeError,
            models.ObjectDoesNotExist,
        ):
            report = None

        if report is not None:
            raise ValidationError(
                "لا يمكن حذف وردية مرتبطة بتقرير تشغيلي."
            )

        return super().delete(
            *args,
            **kwargs,
        )

    @property
    def is_seasonal(self) -> bool:
        """
        هل الوردية موسمية؟
        """
        return (
            self.category
            == self.ShiftCategory.SEASONAL
        )

    @property
    def duration_minutes(self) -> int:
        """
        مدة الوردية بالدقائق.

        تعيد صفرًا إذا لم تكتمل بيانات الوقت.
        """
        datetime_range = self.get_datetime_range()

        if datetime_range is None:
            return 0

        start_datetime, end_datetime = (
            datetime_range
        )

        duration = (
            end_datetime - start_datetime
        )

        return int(
            duration.total_seconds() // 60
        )

    @property
    def effective_start_time(self):
        """
        وقت البداية المستخدم فعليًا.
        """
        if self.start_time:
            return self.start_time

        if (
            self.shift_type_id
            and self.shift_type.start_time
        ):
            return self.shift_type.start_time

        return None

    @property
    def effective_end_time(self):
        """
        وقت النهاية المستخدم فعليًا.
        """
        if self.end_time:
            return self.end_time

        if (
            self.shift_type_id
            and self.shift_type.end_time
        ):
            return self.shift_type.end_time

        return None

    def __str__(self) -> str:
        shift_name = (
            self.shift_type.name
            if self.shift_type_id
            else "وردية"
        )

        shift_date = (
            self.date.strftime("%Y-%m-%d")
            if self.date
            else "بدون تاريخ"
        )

        start_label = (
            self.start_time.strftime("%H:%M")
            if self.start_time
            else "--:--"
        )

        end_label = (
            self.end_time.strftime("%H:%M")
            if self.end_time
            else "--:--"
        )

        return (
            f"{shift_name} - "
            f"{shift_date} - "
            f"{start_label} إلى {end_label}"
        )