from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone


class ExportLog(models.Model):
    """
    سجل مركزي لجميع عمليات التصدير داخل منصة أبواب.

    يسجل:
    - المستخدم.
    - القسم ونوع التقرير.
    - صيغة الملف.
    - الفلاتر المستخدمة.
    - عدد السجلات.
    - وقت الطلب والبداية والانتهاء.
    - حالة التصدير.
    - رسالة الخطأ.
    - حجم الملف.
    - اسم ومسار الملف.
    - عنوان IP والمتصفح.
    - عدد مرات التنزيل.
    """

    class ExportFormat(models.TextChoices):
        EXCEL = "excel", "Excel"
        PDF = "pdf", "PDF"
        CSV = "csv", "CSV"
        WORD = "word", "Word"

    class ExportStatus(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد المعالجة"
        SUCCESS = "success", "مكتمل"
        FAILED = "failed", "فشل"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_logs",
        verbose_name="المستخدم",
    )

    module = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="القسم",
        help_text="اسم القسم أو السجل الذي تم تصديره.",
    )

    report_key = models.SlugField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="معرّف التقرير",
        help_text="معرّف برمجي ثابت لنوع التقرير.",
    )

    report_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="اسم التقرير",
        help_text="الاسم الظاهر للمستخدم مثل سجل الموظفين.",
    )

    file_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="اسم الملف",
    )

    file = models.FileField(
        upload_to="exports/%Y/%m/%d/",
        null=True,
        blank=True,
        verbose_name="الملف المحفوظ",
        help_text="نسخة محفوظة من الملف لإعادة تنزيله لاحقًا.",
    )

    storage_path = models.CharField(
        max_length=1000,
        blank=True,
        verbose_name="مسار الملف",
        help_text="مسار الملف داخل وسيط التخزين.",
    )

    export_format = models.CharField(
        max_length=20,
        choices=ExportFormat.choices,
        default=ExportFormat.EXCEL,
        db_index=True,
        verbose_name="صيغة التصدير",
    )

    status = models.CharField(
        max_length=20,
        choices=ExportStatus.choices,
        default=ExportStatus.PROCESSING,
        db_index=True,
        verbose_name="حالة العملية",
    )

    records_count = models.PositiveIntegerField(
        default=0,
        verbose_name="عدد السجلات",
    )

    file_size = models.PositiveBigIntegerField(
        default=0,
        verbose_name="حجم الملف بالبايت",
    )

    filters = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="فلاتر وخيارات التصدير",
        help_text=(
            "يحفظ الفترة والوردية والمنطقة والحالات "
            "والموظف وبقية خيارات التصدير."
        ),
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="بيانات إضافية",
        help_text=(
            "بيانات إضافية مثل مؤشرات الأداء "
            "ومعلومات الوردية والمعاينة."
        ),
    )

    error_message = models.TextField(
        blank=True,
        verbose_name="تفاصيل الخطأ",
    )

    requested_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP",
    )

    user_agent = models.TextField(
        blank=True,
        verbose_name="بيانات المتصفح",
    )

    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="عدد مرات التنزيل",
    )

    last_downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخر تنزيل",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="وقت طلب التصدير",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت بدء المعالجة",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت اكتمال التصدير",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "عملية تصدير"
        verbose_name_plural = "سجل عمليات التصدير"

        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="export_status_date_idx",
            ),
            models.Index(
                fields=["export_format", "created_at"],
                name="export_format_date_idx",
            ),
            models.Index(
                fields=["module", "created_at"],
                name="export_module_date_idx",
            ),
            models.Index(
                fields=["report_key", "created_at"],
                name="export_report_date_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="export_user_date_idx",
            ),
        ]

    def __str__(self) -> str:
        report_label = (
            self.report_name
            or self.module
            or self.report_key
            or "تقرير"
        )

        return (
            f"{report_label} - "
            f"{self.get_export_format_display()} - "
            f"{self.get_status_display()}"
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        مزامنة اسم ومسار الملف قبل الحفظ.
        """
        if self.file:
            if not self.file_name:
                self.file_name = Path(self.file.name).name

            self.storage_path = self.file.name or ""

            try:
                self.file_size = self.file.size or self.file_size
            except (FileNotFoundError, OSError, ValueError):
                pass

        if not self.report_name:
            self.report_name = self.module or self.report_key

        super().save(*args, **kwargs)

    @property
    def extension(self) -> str:
        """
        إرجاع امتداد الملف بأحرف صغيرة.
        """
        return Path(
            self.file_name or self.storage_path or ""
        ).suffix.lower()

    @property
    def formatted_file_size(self) -> str:
        """
        عرض حجم الملف بصيغة مقروءة.
        """
        size = max(int(self.file_size or 0), 0)

        if size < 1024:
            return f"{size} بايت"

        if size < 1024**2:
            return f"{size / 1024:.1f} كيلوبايت"

        if size < 1024**3:
            return f"{size / (1024**2):.1f} ميجابايت"

        return f"{size / (1024**3):.1f} جيجابايت"

    @property
    def is_ready_for_download(self) -> bool:
        """
        التحقق من نجاح العملية ووجود ملف محفوظ.
        """
        return (
            self.status == self.ExportStatus.SUCCESS
            and bool(self.file)
        )

    @property
    def duration_seconds(self) -> float | None:
        """
        مدة المعالجة الفعلية بالثواني.
        """
        start_time = self.started_at or self.created_at

        if not start_time or not self.completed_at:
            return None

        duration = self.completed_at - start_time
        return round(
            max(duration.total_seconds(), 0),
            2,
        )

    @property
    def formatted_duration(self) -> str:
        """
        عرض مدة التنفيذ بصيغة مقروءة.
        """
        duration = self.duration_seconds

        if duration is None:
            return "—"

        if duration < 60:
            return f"{duration:.2f} ثانية"

        minutes = int(duration // 60)
        seconds = int(duration % 60)

        if minutes < 60:
            return f"{minutes} دقيقة و{seconds} ثانية"

        hours = minutes // 60
        remaining_minutes = minutes % 60

        return (
            f"{hours} ساعة "
            f"و{remaining_minutes} دقيقة"
        )

    def mark_processing(
        self,
        *,
        save: bool = True,
    ) -> None:
        """
        تحويل العملية إلى قيد المعالجة.
        """
        self.status = self.ExportStatus.PROCESSING
        self.started_at = timezone.now()
        self.completed_at = None
        self.error_message = ""

        if save:
            self.save(
                update_fields=[
                    "status",
                    "started_at",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

    def mark_success(
        self,
        *,
        records_count: int = 0,
        file_size: int = 0,
        file_name: str | None = None,
        storage_path: str | None = None,
        metadata: dict[str, Any] | None = None,
        save: bool = True,
    ) -> None:
        """
        تحويل العملية إلى مكتملة وتحديث بيانات الملف.
        """
        self.status = self.ExportStatus.SUCCESS

        if not self.started_at:
            self.started_at = self.created_at or timezone.now()

        self.records_count = max(
            int(records_count or 0),
            0,
        )

        self.file_size = max(
            int(file_size or 0),
            0,
        )

        if file_name is not None:
            self.file_name = str(file_name)

        if storage_path is not None:
            self.storage_path = str(storage_path)

        if metadata is not None:
            self.metadata = metadata

        if self.file:
            self.storage_path = (
                self.storage_path
                or self.file.name
                or ""
            )

            self.file_name = (
                self.file_name
                or Path(self.file.name).name
            )

            if not self.file_size:
                try:
                    self.file_size = self.file.size
                except (
                    FileNotFoundError,
                    OSError,
                    ValueError,
                ):
                    pass

        self.completed_at = timezone.now()
        self.error_message = ""

        if save:
            self.save(
                update_fields=[
                    "status",
                    "started_at",
                    "records_count",
                    "file_size",
                    "file_name",
                    "storage_path",
                    "metadata",
                    "completed_at",
                    "error_message",
                    "updated_at",
                ]
            )

    def mark_failed(
        self,
        error_message: str = "",
        *,
        metadata: dict[str, Any] | None = None,
        save: bool = True,
    ) -> None:
        """
        تحويل العملية إلى فاشلة مع حفظ الخطأ.
        """
        self.status = self.ExportStatus.FAILED

        if not self.started_at:
            self.started_at = self.created_at or timezone.now()

        self.error_message = str(
            error_message or ""
        )[:5000]

        if metadata is not None:
            self.metadata = metadata

        self.completed_at = timezone.now()

        if save:
            self.save(
                update_fields=[
                    "status",
                    "started_at",
                    "error_message",
                    "metadata",
                    "completed_at",
                    "updated_at",
                ]
            )

    def register_download(self) -> None:
        """
        تسجيل عملية تنزيل بطريقة آمنة عند تزامن الطلبات.
        """
        now = timezone.now()

        type(self).objects.filter(
            pk=self.pk
        ).update(
            download_count=F("download_count") + 1,
            last_downloaded_at=now,
            updated_at=now,
        )

        self.refresh_from_db(
            fields=[
                "download_count",
                "last_downloaded_at",
                "updated_at",
            ]
        )