from django.core.validators import RegexValidator
from django.db import models


class SystemConfiguration(models.Model):
    """Typed, singleton configuration for safe day-to-day platform settings."""

    SINGLETON_PK = 1

    class Language(models.TextChoices):
        ARABIC = "ar", "العربية"
        ENGLISH = "en", "English"

    organization_name = models.CharField(max_length=180, default="إدارة الأبواب")
    platform_name = models.CharField(max_length=120, default="منصة أبواب")
    timezone = models.CharField(max_length=64, default="Asia/Riyadh")
    default_language = models.CharField(
        max_length=5,
        choices=Language.choices,
        default=Language.ARABIC,
    )
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(
        max_length=24,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?[0-9 ()-]{7,24}$",
                message="أدخل رقم تواصل صحيحًا.",
            )
        ],
    )
    communications_enabled = models.BooleanField(default=True)
    email_notifications_enabled = models.BooleanField(default=True)
    sms_notifications_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات النظام"
        verbose_name_plural = "إعدادات النظام"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pk=1),
                name="core_systemconfiguration_singleton_pk",
            )
        ]

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return "إعدادات النظام"
