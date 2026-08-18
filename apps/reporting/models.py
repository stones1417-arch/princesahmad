from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.scheduling.models import ShiftPlan


class ShiftReport(models.Model):
    """
    تقرير تشغيلي مرتبط بوردية منتهية،
    أو تقرير إداري يدوي مستقل.

    القواعد الأساسية:
    - التقرير التشغيلي يجب أن يرتبط بوردية منتهية.
    - لا يمكن إنشاء أكثر من تقرير للوردية نفسها.
    - التقرير النهائي أو المعتمد لا يمكن تعديله مباشرة.
    - التقرير المعتمد لا يمكن حذفه.
    - الاعتماد يتطلب صلاحية can_approve_shift_report.
    - حقول الاعتماد لا تُملأ إلا عند اعتماد التقرير.
    """

    class ReportStatus(models.TextChoices):
        DRAFT = "draft", "مسودة"
        FINAL = "final", "نهائي"
        APPROVED = "approved", "معتمد"

    class ReportType(models.TextChoices):
        OPERATIONAL = "operational", "تقرير تشغيلي"
        MANUAL = "manual", "تقرير إداري"

    class OperationalSection(models.TextChoices):
        ALL = "all", "الكل"
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"

    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.OPERATIONAL,
        db_index=True,
        verbose_name="نوع التقرير",
    )

    operational_section = models.CharField(
        max_length=10,
        choices=OperationalSection.choices,
        default=OperationalSection.ALL,
        db_index=True,
        verbose_name="نطاق القسم التشغيلي",
    )

    shift_plan = models.OneToOneField(
        ShiftPlan,
        on_delete=models.CASCADE,
        related_name="report",
        db_index=True,
        null=True,
        blank=True,
        verbose_name="الوردية",
    )

    report_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        db_index=True,
        verbose_name="رقم التقرير",
    )

    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.DRAFT,
        db_index=True,
        verbose_name="حالة التقرير",
    )

    total_doors = models.PositiveIntegerField(
        default=0,
        verbose_name="إجمالي الأبواب",
    )

    open_doors = models.PositiveIntegerField(
        default=0,
        verbose_name="الأبواب المفتوحة",
    )

    closed_doors = models.PositiveIntegerField(
        default=0,
        verbose_name="الأبواب المغلقة",
    )

    maintenance_doors = models.PositiveIntegerField(
        default=0,
        verbose_name="الأبواب تحت الصيانة",
    )

    total_employees = models.PositiveIntegerField(
        default=0,
        verbose_name="إجمالي الموظفين",
    )

    total_maintenance_requests = models.PositiveIntegerField(
        default=0,
        verbose_name="إجمالي طلبات الصيانة",
    )

    completed_maintenance_requests = models.PositiveIntegerField(
        default=0,
        verbose_name="طلبات الصيانة المنجزة",
    )

    summary = models.TextField(
        blank=True,
        verbose_name="الملخص",
    )

    recommendations = models.TextField(
        blank=True,
        verbose_name="التوصيات",
    )

    snapshot_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name="نسخة البيانات التشغيلية",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_shift_reports",
        verbose_name="أنشئ بواسطة",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_shift_reports",
        verbose_name="اعتمد بواسطة",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الاعتماد",
    )

    class Meta:
        ordering = [
            "-created_at",
            "-id",
        ]

        verbose_name = "تقرير وردية"
        verbose_name_plural = "تقارير الورديات"

        indexes = [
            models.Index(
                fields=["status"],
                name="report_status_idx",
            ),
            models.Index(
                fields=["report_type"],
                name="report_type_idx",
            ),
            models.Index(
                fields=["created_at"],
                name="report_created_idx",
            ),
            models.Index(
                fields=["shift_plan"],
                name="report_shift_idx",
            ),
        ]

        permissions = [
            (
                "can_generate_shift_report",
                "يمكن إنشاء تقرير وردية",
            ),
            (
                "can_approve_shift_report",
                "يمكن اعتماد التقرير",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                name=(
                    "shiftreport_approved_fields_"
                    "only_when_approved"
                ),
                condition=(
                    Q(
                        status="approved",
                        approved_by__isnull=False,
                        approved_at__isnull=False,
                    )
                    |
                    Q(
                        status__in=[
                            "draft",
                            "final",
                        ],
                        approved_by__isnull=True,
                        approved_at__isnull=True,
                    )
                ),
            ),
            models.CheckConstraint(
                name="shiftreport_open_doors_lte_total",
                condition=Q(
                    open_doors__lte=models.F(
                        "total_doors"
                    )
                ),
            ),
            models.CheckConstraint(
                name="shiftreport_closed_doors_lte_total",
                condition=Q(
                    closed_doors__lte=models.F(
                        "total_doors"
                    )
                ),
            ),
            models.CheckConstraint(
                name="shiftreport_maintenance_doors_lte_total",
                condition=Q(
                    maintenance_doors__lte=models.F(
                        "total_doors"
                    )
                ),
            ),
            models.CheckConstraint(
                name="shiftreport_completed_maintenance_lte_total",
                condition=Q(
                    completed_maintenance_requests__lte=models.F(
                        "total_maintenance_requests"
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.report_number or 'بدون رقم'} - "
            f"{self.get_report_type_display()}"
        )

    # ==========================================================
    # المؤشرات
    # ==========================================================

    @property
    def maintenance_completion_rate(self) -> float:
        """
        نسبة طلبات الصيانة المنجزة.
        """

        if not self.total_maintenance_requests:
            return 0.0

        return round(
            (
                self.completed_maintenance_requests
                / self.total_maintenance_requests
            )
            * 100,
            2,
        )

    @property
    def doors_open_rate(self) -> float:
        """
        نسبة الأبواب المفتوحة من إجمالي الأبواب.
        """

        if not self.total_doors:
            return 0.0

        return round(
            (
                self.open_doors
                / self.total_doors
            )
            * 100,
            2,
        )

    @property
    def accounted_doors(self) -> int:
        """
        عدد الأبواب التي تم احتساب حالتها في التقرير.
        """

        return (
            self.open_doors
            + self.closed_doors
            + self.maintenance_doors
        )

    @property
    def unaccounted_doors(self) -> int:
        """
        الأبواب التي لم تدخل ضمن الحالات الثلاث الأساسية.
        """

        return max(
            self.total_doors
            - self.accounted_doors,
            0,
        )

    @property
    def is_approved(self) -> bool:
        return (
            self.status
            == self.ReportStatus.APPROVED
        )

    @property
    def is_final(self) -> bool:
        return (
            self.status
            == self.ReportStatus.FINAL
        )

    @property
    def is_locked(self) -> bool:
        """
        التقرير النهائي أو المعتمد يعتبر مقفلًا.
        """

        return self.status in {
            self.ReportStatus.FINAL,
            self.ReportStatus.APPROVED,
        }

    # ==========================================================
    # التحقق
    # ==========================================================

    def clean(self) -> None:
        """
        التحقق من القواعد التشغيلية للتقرير.
        """

        super().clean()

        errors: dict[str, Any] = {}

        self.summary = str(
            self.summary or ""
        ).strip()

        self.recommendations = str(
            self.recommendations or ""
        ).strip()

        # ------------------------------------------------------
        # التقرير التشغيلي
        # ------------------------------------------------------

        if (
            self.report_type
            == self.ReportType.OPERATIONAL
        ):
            if not self.shift_plan_id:
                errors["shift_plan"] = (
                    "التقرير التشغيلي يجب أن يكون "
                    "مرتبطًا بوردية."
                )

            elif not self.shift_plan.is_finished:
                errors["shift_plan"] = (
                    "لا يمكن إنشاء تقرير تشغيلي "
                    "لوردية غير منتهية."
                )

        # ------------------------------------------------------
        # التقرير الإداري
        # ------------------------------------------------------

        if (
            self.report_type
            == self.ReportType.MANUAL
        ):
            if (
                not self.summary
                and not self.recommendations
            ):
                errors["summary"] = (
                    "التقرير الإداري يحتاج إلى "
                    "ملخص أو توصيات."
                )

        # ------------------------------------------------------
        # أعداد الأبواب
        # ------------------------------------------------------

        if self.accounted_doors > self.total_doors:
            errors["total_doors"] = (
                "مجموع الأبواب المفتوحة والمغلقة "
                "وتحت الصيانة لا يمكن أن يتجاوز "
                "إجمالي الأبواب."
            )

        # ------------------------------------------------------
        # أعداد الصيانة
        # ------------------------------------------------------

        if (
            self.completed_maintenance_requests
            > self.total_maintenance_requests
        ):
            errors[
                "completed_maintenance_requests"
            ] = (
                "طلبات الصيانة المنجزة لا يمكن "
                "أن تتجاوز إجمالي الطلبات."
            )

        # ------------------------------------------------------
        # حقول الاعتماد
        # ------------------------------------------------------

        if (
            self.status
            == self.ReportStatus.APPROVED
        ):
            if not self.approved_by_id:
                errors["approved_by"] = (
                    "يجب تحديد المستخدم الذي اعتمد التقرير."
                )

            if not self.approved_at:
                errors["approved_at"] = (
                    "يجب تسجيل تاريخ اعتماد التقرير."
                )

        else:
            if self.approved_by_id:
                errors["approved_by"] = (
                    "لا يمكن تحديد معتمد لتقرير "
                    "غير معتمد."
                )

            if self.approved_at:
                errors["approved_at"] = (
                    "لا يمكن تسجيل تاريخ اعتماد "
                    "لتقرير غير معتمد."
                )

        if errors:
            raise ValidationError(
                errors
            )

    # ==========================================================
    # توليد رقم التقرير
    # ==========================================================

    def _generate_report_number(self) -> str:
        """
        توليد رقم تقرير يومي متسلسل.

        SR للتقارير التشغيلية.
        MR للتقارير الإدارية.
        """

        today_str = timezone.localtime(
            timezone.now()
        ).strftime("%Y%m%d")

        if (
            self.report_type
            == self.ReportType.MANUAL
        ):
            prefix = f"MR-{today_str}-"

        else:
            prefix = f"SR-{today_str}-"

        existing_numbers = (
            ShiftReport.objects
            .filter(
                report_number__startswith=prefix
            )
            .values_list(
                "report_number",
                flat=True,
            )
        )

        used_sequences: set[int] = set()

        for report_number in existing_numbers:
            try:
                sequence = int(
                    str(report_number).split("-")[-1]
                )
            except (
                TypeError,
                ValueError,
                IndexError,
            ):
                continue

            used_sequences.add(
                sequence
            )

        for sequence in range(
            1,
            10000,
        ):
            if sequence not in used_sequences:
                return (
                    f"{prefix}{sequence:03d}"
                )

        return (
            f"{prefix}"
            f"{timezone.localtime(timezone.now()):%H%M%S%f}"
        )

    # ==========================================================
    # الحفظ
    # ==========================================================

    def save(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        حفظ التقرير بعد تطبيق التحقق الكامل.

        يمنع التعديل المباشر إذا كان التقرير الموجود
        نهائيًا أو معتمدًا.
        """

        with transaction.atomic():
            if self.pk:
                current_report = (
                    ShiftReport.objects
                    .select_for_update()
                    .only(
                        "status",
                    )
                    .get(
                        pk=self.pk
                    )
                )

                if (
                    current_report.status
                    == self.ReportStatus.APPROVED
                ):
                    raise ValidationError(
                        "لا يمكن تعديل تقرير معتمد."
                    )

                if (
                    current_report.status
                    == self.ReportStatus.FINAL
                ):
                    raise ValidationError(
                        "لا يمكن تعديل تقرير نهائي. "
                        "يجب إعادته إلى مسودة من خلال "
                        "إجراء إداري مخصص."
                    )

            if not self.report_number:
                self.report_number = (
                    self._generate_report_number()
                )

            self.full_clean()

            super().save(
                *args,
                **kwargs,
            )

    # ==========================================================
    # تحويل التقرير إلى نهائي
    # ==========================================================

    def finalize(self) -> None:
        """
        تحويل التقرير من مسودة إلى نهائي.
        """

        if not self.pk:
            raise ValidationError(
                "يجب حفظ التقرير قبل تحويله إلى نهائي."
            )

        with transaction.atomic():
            report = (
                ShiftReport.objects
                .select_for_update()
                .get(
                    pk=self.pk
                )
            )

            if (
                report.status
                == self.ReportStatus.APPROVED
            ):
                raise ValidationError(
                    "لا يمكن تعديل تقرير معتمد."
                )

            if (
                report.status
                == self.ReportStatus.FINAL
            ):
                raise ValidationError(
                    "التقرير نهائي بالفعل."
                )

            report.status = (
                self.ReportStatus.FINAL
            )

            report.approved_by = None
            report.approved_at = None

            report.full_clean()

            super(
                ShiftReport,
                report,
            ).save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                ]
            )

            self.status = report.status
            self.approved_by = None
            self.approved_at = None

    # ==========================================================
    # اعتماد التقرير
    # ==========================================================

    def approve(
        self,
        user,
    ) -> None:
        """
        اعتماد تقرير نهائي بواسطة مستخدم مخول.
        """

        if not self.pk:
            raise ValidationError(
                "يجب حفظ التقرير قبل اعتماده."
            )

        if user is None:
            raise ValidationError(
                {
                    "approved_by": (
                        "المستخدم المعتمد مطلوب."
                    )
                }
            )

        if not getattr(
            user,
            "is_authenticated",
            False,
        ):
            raise PermissionDenied(
                "يجب تسجيل الدخول لاعتماد التقرير."
            )

        if not getattr(
            user,
            "is_active",
            False,
        ):
            raise PermissionDenied(
                "لا يمكن الاعتماد بواسطة مستخدم غير نشط."
            )

        if not (
            user.has_perm("reporting.can_approve_shift_report")
            or user.has_perm("roles.approve_report")
        ):
            raise PermissionDenied(
                "ليس لديك صلاحية اعتماد تقارير الورديات."
            )

        with transaction.atomic():
            report = (
                ShiftReport.objects
                .select_for_update()
                .select_related(
                    "approved_by",
                    "shift_plan",
                )
                .get(
                    pk=self.pk
                )
            )

            if (
                report.status
                == self.ReportStatus.APPROVED
            ):
                raise ValidationError(
                    "التقرير معتمد مسبقًا."
                )

            if (
                report.status
                == self.ReportStatus.DRAFT
            ):
                raise ValidationError(
                    "لا يمكن اعتماد تقرير وهو مسودة."
                )

            if (
                report.status
                != self.ReportStatus.FINAL
            ):
                raise ValidationError(
                    "لا يمكن اعتماد التقرير في حالته الحالية."
                )

            report.status = (
                self.ReportStatus.APPROVED
            )

            report.approved_by = user
            report.approved_at = timezone.now()

            report.full_clean()

            super(
                ShiftReport,
                report,
            ).save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                ]
            )

            self.status = report.status
            self.approved_by = user
            self.approved_by_id = user.pk
            self.approved_at = report.approved_at

    # ==========================================================
    # إعادة التقرير إلى مسودة
    # ==========================================================

    def return_to_draft(self) -> None:
        """
        إعادة التقرير النهائي إلى مسودة.

        لا يسمح بإعادة التقرير المعتمد إلى مسودة.
        """

        if not self.pk:
            raise ValidationError(
                "التقرير غير محفوظ."
            )

        with transaction.atomic():
            report = (
                ShiftReport.objects
                .select_for_update()
                .get(
                    pk=self.pk
                )
            )

            if (
                report.status
                == self.ReportStatus.APPROVED
            ):
                raise ValidationError(
                    "لا يمكن إعادة تقرير معتمد إلى مسودة."
                )

            if (
                report.status
                == self.ReportStatus.DRAFT
            ):
                raise ValidationError(
                    "التقرير مسودة بالفعل."
                )

            report.status = (
                self.ReportStatus.DRAFT
            )

            report.approved_by = None
            report.approved_at = None

            report.full_clean()

            super(
                ShiftReport,
                report,
            ).save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                ]
            )

            self.status = report.status
            self.approved_by = None
            self.approved_by_id = None
            self.approved_at = None

    # ==========================================================
    # الحذف
    # ==========================================================

    def delete(
        self,
        using=None,
        keep_parents: bool = False,
    ):
        """
        منع حذف التقارير النهائية أو المعتمدة.
        """

        if self.status == self.ReportStatus.APPROVED:
            raise ValidationError(
                "لا يمكن حذف تقرير معتمد."
            )

        if self.status == self.ReportStatus.FINAL:
            raise ValidationError(
                "لا يمكن حذف تقرير نهائي."
            )

        return super().delete(
            using=using,
            keep_parents=keep_parents,
        )