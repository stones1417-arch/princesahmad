from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_profile_photo_size(image):
    """منع رفع صور شخصية كبيرة بشكل غير مناسب."""
    if image.size > 5 * 1024 * 1024:
        raise ValidationError("حجم الصورة يجب ألا يتجاوز 5 ميجابايت.")


class AccountProfile(models.Model):
    """بيانات العرض الإضافية لحساب المستخدم."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_profile",
        verbose_name="المستخدم",
    )
    photo = models.ImageField(
        upload_to="profiles/%Y/%m/",
        blank=True,
        validators=[validate_profile_photo_size],
        verbose_name="الصورة الشخصية",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ملف حساب"
        verbose_name_plural = "ملفات الحسابات"

    def __str__(self):
        return f"ملف {self.user.username}"


class Role(models.Model):
    """
    الأدوار التشغيلية (موظف – مشرف – رئيس وردية – مدير)
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class UserRole(models.Model):
    """
    ربط المستخدم بالدور
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    class Meta:
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user} - {self.role}"
