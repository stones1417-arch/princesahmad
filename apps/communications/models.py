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

    class OperationalSection(models.TextChoices):
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"
        ALL = "all", "الكل"

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

    section = models.CharField(
        max_length=10,
        choices=OperationalSection.choices,
        default=OperationalSection.ALL,
        db_index=True,
        verbose_name="القسم التشغيلي",
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
            models.Index(fields=["section"]),
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


class CommunicationProvider(models.Model):
    """Non-secret configuration for an external communications provider."""

    name = models.CharField(max_length=100, verbose_name="اسم المزود")
    provider_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="رمز المزود",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    supports_sms = models.BooleanField(default=False, verbose_name="يدعم SMS")
    supports_whatsapp = models.BooleanField(
        default=False,
        verbose_name="يدعم واتساب",
    )
    supports_email = models.BooleanField(
        default=False,
        verbose_name="يدعم البريد الإلكتروني",
    )
    supports_voice = models.BooleanField(default=False, verbose_name="يدعم الصوت")
    supports_face = models.BooleanField(default=False, verbose_name="يدعم التحقق بالوجه")
    supports_nafath = models.BooleanField(default=False, verbose_name="يدعم نفاذ")
    base_url = models.URLField(blank=True, verbose_name="الرابط الأساسي")
    sender_name = models.CharField(max_length=100, blank=True, verbose_name="اسم المرسل")
    timeout_seconds = models.PositiveIntegerField(default=15, verbose_name="مهلة الاتصال")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مزود اتصالات"
        verbose_name_plural = "مزودو الاتصالات"

    def __str__(self):
        return self.name


class MessageTemplate(models.Model):
    """Internal operational-message template; never an Authentica OTP template."""
    class Channel(models.TextChoices):
        SMS = "sms", "رسالة نصية"
        WHATSAPP = "whatsapp", "واتساب"
        EMAIL = "email", "بريد إلكتروني"
        VOICE = "voice", "صوتي"

    class Section(models.TextChoices):
        ALL = "all", "الكل"
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"

    name = models.CharField(max_length=150, verbose_name="اسم القالب")
    code = models.CharField(max_length=100, unique=True, verbose_name="رمز القالب")
    channel = models.CharField(max_length=20, choices=Channel.choices, db_index=True)
    subject = models.CharField(max_length=255, blank=True, verbose_name="الموضوع")
    body = models.TextField(verbose_name="النص")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="نشط")
    section = models.CharField(
        max_length=10,
        choices=Section.choices,
        default=Section.ALL,
        db_index=True,
        verbose_name="القسم",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قالب رسالة"
        verbose_name_plural = "قوالب الرسائل"
        indexes = [models.Index(fields=["channel", "section", "is_active"])]

    def __str__(self):
        return self.name


class CommunicationLog(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "رسالة نصية"
        WHATSAPP = "whatsapp", "واتساب"
        EMAIL = "email", "بريد إلكتروني"
        VOICE = "voice", "صوتي"
        FACE = "face", "تحقق بالوجه"
        NAFATH = "nafath", "نفاذ"

    class Section(models.TextChoices):
        MALE = "male", "رجالي"
        FEMALE = "female", "نسائي"
        ALL = "all", "الكل"

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد الإرسال"
        SENT = "sent", "أرسلت"
        DELIVERED = "delivered", "تم التسليم"
        FAILED = "failed", "فشلت"
        REJECTED = "rejected", "مرفوضة"
        SIMULATED = "simulated", "محاكاة"
        VERIFIED = "verified", "تم التحقق"
        EXPIRED = "expired", "منتهية"
        SKIPPED = "skipped", "تم التخطي"

    recipient_employee = models.ForeignKey(
        "hr.Employee", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="communication_logs", verbose_name="الموظف المستلم",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="received_communication_logs", verbose_name="المستخدم المستلم",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, db_index=True)
    section = models.CharField(max_length=10, choices=Section.choices, default=Section.ALL, db_index=True)
    recipient_address = models.CharField(max_length=254, verbose_name="عنوان المستلم")
    subject = models.CharField(max_length=255, blank=True)
    message_body = models.TextField()
    provider = models.ForeignKey(
        CommunicationProvider, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="communication_logs", verbose_name="المزود",
    )
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    related_assignment = models.ForeignKey(
        "distribution.DoorAssignment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="communication_logs", verbose_name="التكليف المرتبط",
    )
    related_shift = models.ForeignKey(
        "scheduling.ShiftPlan", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="communication_logs", verbose_name="الوردية المرتبطة",
    )
    related_door = models.ForeignKey(
        "locations.Door", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="communication_logs", verbose_name="الباب المرتبط",
    )
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_communication_logs", verbose_name="أنشئ بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سجل اتصال"
        verbose_name_plural = "سجلات الاتصالات"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["channel"]),
            models.Index(fields=["section"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["recipient_employee"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_communication_idempotency_key",
            ),
        ]
        permissions = [
            ("can_view_communications", "Can view communications"),
            ("can_send_sms", "Can send SMS"),
            ("can_send_whatsapp", "Can send WhatsApp"),
            ("can_send_email", "Can send email"),
            ("can_retry_message", "Can retry message"),
            ("can_retry_assignment_message", "Can retry assignment message"),
            ("can_view_communication_errors", "Can view communication errors"),
            ("can_manage_message_templates", "Can manage message templates"),
        ]

    def __str__(self):
        return f"{self.get_channel_display()} #{self.pk}"


class OTPTemplate(models.Model):
    """Provider-independent OTP metadata; never used for operational messages."""

    class Channel(models.TextChoices):
        SMS = "sms", "رسالة نصية"
        WHATSAPP = "whatsapp", "واتساب"
        EMAIL = "email", "بريد إلكتروني"
        VOICE = "voice", "صوتي"

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=100, unique=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    provider_template_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قالب OTP"
        verbose_name_plural = "قوالب OTP"

    def __str__(self):
        return self.name


class OTPVerification(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "رسالة نصية"
        WHATSAPP = "whatsapp", "واتساب"
        EMAIL = "email", "بريد إلكتروني"
        VOICE = "voice", "صوتي"

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        SENT = "sent", "أرسلت"
        VERIFIED = "verified", "تم التحقق"
        FAILED = "failed", "فشلت"
        REJECTED = "rejected", "مرفوضة"
        EXPIRED = "expired", "منتهية"
        SIMULATED = "simulated", "محاكاة"

    class Purpose(models.TextChoices):
        LOGIN = "login", "تسجيل الدخول"
        PASSWORD_RESET = "password_reset", "إعادة تعيين كلمة المرور"
        PHONE_VERIFICATION = "phone_verification", "توثيق الجوال"
        EMAIL_VERIFICATION = "email_verification", "توثيق البريد"
        SENSITIVE_ACTION = "sensitive_action", "إجراء حساس"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="otp_verifications")
    employee = models.ForeignKey("hr.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="otp_verifications")
    channel = models.CharField(max_length=20, choices=Channel.choices, db_index=True)
    recipient_masked = models.CharField(max_length=254)
    provider_request_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    purpose = models.CharField(max_length=30, choices=Purpose.choices, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تحقق OTP"
        verbose_name_plural = "تحققات OTP"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "purpose", "created_at"])]


class IdentityVerification(models.Model):
    class VerificationType(models.TextChoices):
        NAFATH = "nafath", "نفاذ"
        FACE = "face", "تحقق بالوجه"

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        VERIFIED = "verified", "تم التحقق"
        FAILED = "failed", "فشلت"
        REJECTED = "rejected", "مرفوضة"
        EXPIRED = "expired", "منتهية"
        SIMULATED = "simulated", "محاكاة"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="identity_verifications")
    employee = models.ForeignKey("hr.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="identity_verifications")
    provider = models.ForeignKey(CommunicationProvider, on_delete=models.SET_NULL, null=True, blank=True)
    verification_type = models.CharField(max_length=20, choices=VerificationType.choices, db_index=True)
    provider_request_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "تحقق هوية"
        verbose_name_plural = "تحققات الهوية"
        indexes = [models.Index(fields=["verification_type", "status", "requested_at"])]


class CommunicationPreference(models.Model):
    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "واتساب"
        SMS = "sms", "رسالة نصية"
        EMAIL = "email", "بريد إلكتروني"

    employee = models.OneToOneField("hr.Employee", on_delete=models.CASCADE, related_name="communication_preference")
    sms_enabled = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    preferred_channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.SMS)
    allow_fallback = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تفضيل اتصالات"
        verbose_name_plural = "تفضيلات الاتصالات"