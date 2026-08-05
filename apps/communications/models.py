from django.conf import settings
from django.db import models


class Announcement(models.Model):
    """
    تعميم أو إعلان داخلي
    """

    class Priority(models.TextChoices):
        NORMAL = "normal", "عادي"
        IMPORTANT = "important", "مهم"
        URGENT = "urgent", "عاجل"

    title = models.CharField(
        max_length=200,
        verbose_name="عنوان التعميم",
    )

    content = models.TextField(
        verbose_name="محتوى التعميم",
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
        verbose_name="الأولوية",
    )

    # 🆕 المرفق (PDF / Word / صورة ...)
    attachment = models.FileField(
        upload_to="announcements/",
        null=True,
        blank=True,
        verbose_name="المرفق",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشط",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_announcements",
        verbose_name="أنشئ بواسطة",
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
        ordering = ["-created_at"]
        verbose_name = "تعميم"
        verbose_name_plural = "التعاميم"

        indexes = [
            models.Index(fields=["priority"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title

    # 🆕 تحديد نوع الملف (اختياري للعرض)
    @property
    def attachment_type(self):
        if not self.attachment:
            return None

        name = self.attachment.name.lower()

        if name.endswith(".pdf"):
            return "pdf"
        elif name.endswith((".jpg", ".jpeg", ".png")):
            return "image"
        elif name.endswith((".doc", ".docx")):
            return "word"
        elif name.endswith((".xls", ".xlsx")):
            return "excel"
        else:
            return "file"