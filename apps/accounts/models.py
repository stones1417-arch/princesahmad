from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


def validate_profile_photo_size(image):
    """
    منع رفع صور شخصية كبيرة بشكل غير مناسب.
    """

    if image.size > 5 * 1024 * 1024:
        raise ValidationError(
            "حجم الصورة يجب ألا يتجاوز 5 ميجابايت."
        )


phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message=(
        "رقم الجوال يجب أن يكون بالصيغة الدولية E.164، "
        "مثال: +9665XXXXXXXX."
    ),
)


class AccountProfile(models.Model):
    """
    بيانات العرض والاتصال الإضافية لحساب المستخدم.

    phone_number يستخدم كرقم اتصال للحسابات
    التي لا ترتبط بسجل Employee، مثل بعض
    حسابات الإدارة.

    موظفو النظام يستمرون باستخدام
    Employee.phone_number كمصدر أساسي.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_profile",
        verbose_name="المستخدم",
    )

    photo = models.ImageField(
        upload_to="profiles/%Y/%m/",
        blank=True,
        validators=[
            validate_profile_photo_size,
        ],
        verbose_name="الصورة الشخصية",
    )

    phone_number = models.CharField(
        max_length=16,
        blank=True,
        validators=[
            phone_validator,
        ],
        verbose_name="رقم الجوال",
        help_text=(
            "استخدم الصيغة الدولية، "
            "مثال: +9665XXXXXXXX."
        ),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "ملف حساب"
        verbose_name_plural = "ملفات الحسابات"

    def clean(self):
        super().clean()

        self.phone_number = (
            self.phone_number
            or ""
        ).strip()

    def __str__(self):
        return (
            f"ملف {self.user.username}"
        )


class AccountRegistrationRequest(models.Model):
    """طلب إنشاء حساب جديد يخضع للمراجعة الإدارية قبل التفعيل."""

    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        NEEDS_EDIT = "needs_edit", "تحتاج مراجعة"
        APPROVED = "approved", "موافق عليه"
        REJECTED = "rejected", "مرفوض"
        CANCELLED = "cancelled", "ملغي"

    class Gender(models.TextChoices):
        MALE = "male", "ذكر"
        FEMALE = "female", "أنثى"

    full_name = models.CharField(
        max_length=150,
        verbose_name="الاسم الكامل",
    )
    employee_number = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="الرقم الوظيفي",
    )
    requested_username = models.CharField(
        max_length=150,
        db_index=True,
        verbose_name="اسم المستخدم المطلوب",
    )
    email = models.EmailField(
        max_length=255,
        db_index=True,
        verbose_name="البريد الإلكتروني",
    )
    phone_number = models.CharField(
        max_length=16,
        validators=[phone_validator],
        verbose_name="رقم الجوال",
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        default=Gender.MALE,
        db_index=True,
        verbose_name="الجنس",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="حالة الطلب",
    )
    review_notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات المراجعة",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_account_registration_requests",
        verbose_name="راجع الطلب بواسطة",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ المراجعة",
    )
    created_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_account_requests",
        verbose_name="المستخدم الذي تم إنشاؤه",
    )
    linked_employee = models.OneToOneField(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_registration_request",
        verbose_name="سجل الموظف المرتبط",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الطلب",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب إنشاء حساب"
        verbose_name_plural = "طلبات إنشاء الحساب"

    def clean(self):
        super().clean()
        self.full_name = (self.full_name or "").strip()
        self.employee_number = (self.employee_number or "").strip()
        self.requested_username = (self.requested_username or "").strip().lower()
        self.email = (self.email or "").strip().lower()
        self.phone_number = (self.phone_number or "").strip()
        self.review_notes = (self.review_notes or "").strip()

    def __str__(self):
        return f"{self.full_name} ({self.requested_username})"


class TwoFactorAuditLog(models.Model):
    class Event(models.TextChoices):
        REQUIRED = "2fa_required", "2FA required"
        SEND_STARTED = "2fa_send_started", "OTP send started"
        SEND_SUCCEEDED = "2fa_send_succeeded", "OTP send succeeded"
        SEND_FAILED = "2fa_send_failed", "OTP send failed"
        VERIFY_STARTED = "2fa_verify_started", "OTP verification started"
        VERIFY_SUCCEEDED = "2fa_verify_succeeded", "OTP verification succeeded"
        VERIFY_FAILED = "2fa_verify_failed", "OTP verification failed"
        RATE_LIMITED = "2fa_rate_limited", "Rate limited"
        EXPIRED = "2fa_expired", "OTP expired"
        REPLAY_BLOCKED = "2fa_replay_blocked", "Replay blocked"
        MAX_ATTEMPTS = "2fa_max_attempts_reached", "Maximum attempts reached"
        CHANNEL_CHANGED = "2fa_channel_changed", "Channel changed"
        RESEND_REQUESTED = "2fa_resend_requested", "Resend requested"
        PENDING_EXPIRED = "2fa_pending_session_expired", "Pending session expired"
        SESSION_COMPLETED = "2fa_session_completed", "Session completed"
        INVALID_SESSION = "2fa_invalid_session", "Invalid pending session"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="two_factor_audit_logs",
    )
    event = models.CharField(max_length=40, choices=Event.choices, db_index=True)
    channel = models.CharField(max_length=20, blank=True, db_index=True)
    status = models.CharField(max_length=20, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["event", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event} #{self.pk}"


class Role(models.Model):
    """
    الأدوار التشغيلية
    (موظف – مشرف – رئيس وردية – مدير)
    """

    name = models.CharField(
        max_length=50,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    def __str__(self):
        return self.name


class UserRole(models.Model):
    """
    ربط المستخدم بالدور.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = (
            "user",
            "role",
        )

    def __str__(self):
        return (
            f"{self.user} - {self.role}"
        )