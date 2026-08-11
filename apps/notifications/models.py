from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    إشعارات النظام
    """

    class Level(models.TextChoices):
        INFO = "info", "معلومات"
        SUCCESS = "success", "نجاح"
        WARNING = "warning", "تنبيه"
        DANGER = "danger", "خطر"

    class OperationalSection(models.TextChoices):
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"
        ALL = "all", "الكل"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="المستخدم",
    )

    title = models.CharField(
        max_length=200,
        verbose_name="العنوان",
    )

    message = models.TextField(
        verbose_name="الرسالة",
    )

    level = models.CharField(
        max_length=20,
        choices=Level.choices,
        default=Level.INFO,
        db_index=True,
        verbose_name="المستوى",
    )

    section = models.CharField(
        max_length=10,
        choices=OperationalSection.choices,
        default=OperationalSection.ALL,
        db_index=True,
        verbose_name="القسم التشغيلي",
    )

    url = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="رابط الانتقال",
    )

    is_read = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="تمت القراءة",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ القراءة",
    )

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"

        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["level"]),
            models.Index(fields=["section"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.user}"

    def mark_as_read(self):
        if self.is_read:
            return

        from django.utils import timezone

        self.is_read = True
        self.read_at = timezone.now()

        self.save(
            update_fields=[
                "is_read",
                "read_at",
            ]
        )