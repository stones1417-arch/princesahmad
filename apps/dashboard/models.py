from django.conf import settings
from django.db import models


class SystemActivityLog(models.Model):
    """
    سجل النشاط العام للمنصة.
    """

    class ActionType(models.TextChoices):
        CREATE = "create", "إنشاء"
        UPDATE = "update", "تعديل"
        DELETE = "delete", "حذف"
        EXPORT = "export", "تصدير"
        APPROVE = "approve", "اعتماد"
        LOGIN = "login", "تسجيل دخول"
        LOGOUT = "logout", "تسجيل خروج"
        OTHER = "other", "أخرى"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_activity_logs",
        verbose_name="المستخدم",
    )

    module = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="القسم",
    )

    action = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        db_index=True,
        verbose_name="نوع العملية",
    )

    description = models.TextField(
        verbose_name="وصف العملية",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="التاريخ",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل نشاط"
        verbose_name_plural = "سجل نشاط النظام"

        indexes = [
            models.Index(fields=["module"]),
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.module} - "
            f"{self.get_action_display()}"
        )