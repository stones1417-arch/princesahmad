from __future__ import annotations

import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.communications.models import OTPVerification
from apps.communications.providers.authentica import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
)
from apps.communications.services.delivery_service import get_provider
from apps.communications.services.otp_service import (
    AuthenticaOTPService,
    OTPRateLimitedError,
    OTPResendCooldownError,
    VerificationNotConfiguredError,
)
from apps.communications.services.otp_validation import (
    OTPRecipientValidationError,
    normalize_saudi_phone_number,
)
from apps.hr.forms import EmployeeForm
from apps.hr.models import Employee
from apps.roles.models import Role
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.role_manager import assign_role_to_user
from apps.roles.services.section_access import get_allowed_sections

from .forms import (
    ProfileContactForm,
    ProfilePhotoForm,
)
from .models import AccountProfile
from .services.two_factor_audit_service import record_2fa_event
from .services.two_factor_readiness import (
    get_user_otp_channels,
    is_user_2fa_ready,
)
from .security import (
    clear_login_failures,
    clear_two_factor_verification,
    has_completed_two_factor,
    login_is_limited,
    mark_two_factor_verified,
    record_login_failure,
    requires_two_factor,
)


security_logger = logging.getLogger(
    "platform.security"
)


# ============================================================
# Two-Factor Authentication
# ============================================================

TWO_FACTOR_SESSION_KEY = (
    "authentica_two_factor_pending"
)


def _pilot_user_ids() -> set[int]:
    """
    إرجاع IDs مستخدمي Pilot Mode بصورة آمنة.
    """

    configured_ids = getattr(
        settings,
        "AUTHENTICA_2FA_PILOT_USER_IDS",
        (),
    ) or ()

    result: set[int] = set()

    for value in configured_ids:
        try:
            result.add(
                int(value)
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

    return result


def _requires_two_factor(
    user,
) -> bool:
    """
    تحديد هل المستخدم مشمول بالتحقق الثنائي.

    الأولوية:
    1. Global 2FA
    2. Pilot Mode
    3. Pilot User IDs
    4. Pilot Superusers
    5. Pilot Staff
    """

    required = requires_two_factor(user)
    if required:
        security_logger.info(
            "Two-factor required by policy.",
            extra={"event": "2fa_required", "user_id": user.pk},
        )
    return required


# ============================================================
# Account / Employee Helpers
# ============================================================

def _get_employee(
    user,
):
    """
    إرجاع سجل Employee إن كان موجودًا.

    حسابات الإدارة قد لا تملك Employee.
    """

    try:
        return user.employee

    except (
        AttributeError,
        Employee.DoesNotExist,
    ):
        return None


def _get_account_profile(
    user,
):
    """
    إرجاع AccountProfile إن كان موجودًا.
    """

    try:
        return user.account_profile

    except (
        AttributeError,
        AccountProfile.DoesNotExist,
    ):
        return None


def _account_phone_number(
    user,
) -> str:
    """
    رقم الجوال المستخدم للاتصالات.

    الأولوية:
    Employee.phone_number
    ثم
    AccountProfile.phone_number
    """

    employee = _get_employee(
        user
    )

    if employee:
        employee_phone = (
            getattr(
                employee,
                "phone_number",
                "",
            )
            or ""
        ).strip()

        if employee_phone:
            return employee_phone

    account_profile = (
        _get_account_profile(
            user
        )
    )

    if account_profile:
        return (
            getattr(
                account_profile,
                "phone_number",
                "",
            )
            or ""
        ).strip()

    return ""


def _account_email(
    user,
) -> str:
    """
    البريد المستخدم للـOTP.

    الأولوية:
    Employee.email
    ثم
    User.email
    """

    employee = _get_employee(
        user
    )

    if employee:
        employee_email = (
            getattr(
                employee,
                "email",
                "",
            )
            or ""
        ).strip()

        if employee_email:
            return employee_email

    return (
        getattr(
            user,
            "email",
            "",
        )
        or ""
    ).strip()


# ============================================================
# OTP Channels
# ============================================================

def _employee_otp_channels(
    user,
) -> list[str]:
    """
    إرجاع قنوات OTP المتاحة.

    SMS وWhatsApp:
    Employee.phone_number أو AccountProfile.phone_number.

    Email:
    Employee.email أو User.email.
    """

    allowed_channels = {
        str(channel)
        .strip()
        .lower()
        for channel in getattr(
            settings,
            "AUTHENTICA_OTP_ALLOWED_CHANNELS",
            (),
        )
        if str(channel).strip()
    }

    channels: list[str] = []

    phone_number = (
        _account_phone_number(
            user
        )
    )

    email = (
        _account_email(
            user
        )
    )

    if phone_number:
        if "sms" in allowed_channels:
            channels.append(
                "sms"
            )

        if (
            "whatsapp"
            in allowed_channels
        ):
            channels.append(
                "whatsapp"
            )

    if (
        email
        and "email" in allowed_channels
    ):
        channels.append(
            "email"
        )

    return channels


def _preferred_otp_channel(
    user,
    channels: list[str],
) -> str:
    """
    تحديد القناة المفضلة للمستخدم.
    """

    if not channels:
        raise VerificationNotConfiguredError(
            "لا توجد قناة OTP متاحة."
        )

    employee = _get_employee(
        user
    )

    preference = None

    if employee:
        preference = getattr(
            employee,
            "communication_preference",
            None,
        )

    preferred_channel = getattr(
        preference,
        "preferred_channel",
        None,
    )

    preferred_channel = str(
        preferred_channel
        or ""
    ).strip().lower()

    if preferred_channel in channels:
        return preferred_channel

    return channels[0]


def _otp_recipient(
    user,
    channel: str,
) -> str:
    """
    إرجاع المستلم الصحيح للقناة.
    """

    channel = str(
        channel
        or ""
    ).strip().lower()

    if channel == "email":
        return _account_email(
            user
        )

    if channel in {
        "sms",
        "whatsapp",
    }:
        return _account_phone_number(
            user
        )

    return ""


# ============================================================
# Pending Two Factor Session
# ============================================================

def _pending_two_factor(
    request,
):
    """
    استرجاع جلسة التحقق المعلقة.
    """

    pending = request.session.get(
        TWO_FACTOR_SESSION_KEY
    )

    if not pending:
        return None, None

    created_at = pending.get("created_at")
    if not isinstance(created_at, (int, float)) or time.time() - created_at > settings.AUTHENTICA_2FA_PENDING_SESSION_AGE:
        request.session.pop(TWO_FACTOR_SESSION_KEY, None)
        user = User.objects.filter(pk=pending.get("user_id")).first()
        record_2fa_event(
            user=user,
            event="2fa_pending_session_expired",
            request=request,
        )
        return None, None

    try:
        user_id = pending[
            "user_id"
        ]

        user = User.objects.get(
            pk=user_id,
            is_active=True,
        )

    except (
        KeyError,
        TypeError,
        ValueError,
        User.DoesNotExist,
    ):
        request.session.pop(
            TWO_FACTOR_SESSION_KEY,
            None,
        )
        record_2fa_event(
            user=User.objects.filter(pk=pending.get("user_id")).first(),
            event="2fa_invalid_session",
            request=request,
        )

        return None, None

    return user, pending


def _two_factor_context(
    user,
    pending,
) -> dict:
    """
    Context صفحة التحقق الثنائي.
    """

    verification = None

    verification_id = pending.get(
        "verification_id"
    )

    if verification_id:
        verification = (
            OTPVerification.objects
            .filter(
                pk=verification_id,
                user=user,
                purpose=(
                    OTPVerification
                    .Purpose
                    .LOGIN
                ),
            )
            .first()
        )

    return {
        "channels": get_user_otp_channels(user),
        "selected_channel": (
            pending.get(
                "channel"
            )
        ),
        "verification": (
            verification
        ),
    }


def _request_login_otp(
    user,
    pending: dict,
    channel: str,
) -> None:
    """
    إرسال OTP لتسجيل الدخول.

    لا يتم تسجيل recipient أو OTP.
    """

    channels = get_user_otp_channels(user)

    channel = str(
        channel
        or ""
    ).strip().lower()

    if channel not in channels:
        raise VerificationNotConfiguredError(
            "قناة OTP غير متاحة."
        )

    employee = _get_employee(
        user
    )

    recipient = _otp_recipient(
        user,
        channel,
    )

    if not recipient:
        raise VerificationNotConfiguredError(
            "بيانات قناة OTP غير مكتملة."
        )

    verification = (
        AuthenticaOTPService(
            get_provider()
        )
        .request_otp(
            user=user,
            employee=employee,
            channel=channel,
            recipient=recipient,
            purpose=(
                OTPVerification
                .Purpose
                .LOGIN
            ),
        )
    )

    pending[
        "channel"
    ] = channel

    pending[
        "verification_id"
    ] = verification.pk

    security_logger.info(
        "Two-factor OTP requested.",
        extra={
            "event": (
                "two_factor_otp_requested"
            ),
            "user_id": user.pk,
            "channel": channel,
        },
    )


def _complete_login(
    request,
    user,
    pending,
):
    """
    إنشاء جلسة تسجيل الدخول النهائية
    بعد نجاح OTP فقط.
    """

    request.session.pop(
        TWO_FACTOR_SESSION_KEY,
        None,
    )

    mark_two_factor_verified(
        request,
        user,
    )

    request.session.cycle_key()

    login(
        request,
        user,
    )

    record_2fa_event(
        user=user,
        event="2fa_session_completed",
        channel=pending.get("channel"),
        request=request,
        metadata={"verification_id": pending.get("verification_id")},
    )

    if pending.get(
        "remember_me"
    ):
        request.session.set_expiry(
            60 * 60 * 24 * 30
        )

    else:
        request.session.set_expiry(
            0
        )

    clear_login_failures(
        request,
        user.username,
    )

    security_logger.info(
        (
            "User authenticated after "
            "two-factor verification."
        ),
        extra={
            "event": (
                "login_succeeded_2fa"
            ),
            "user_id": user.pk,
        },
    )

    security_logger.info(
        "Two-factor login completed.",
        extra={
            "event": "two_factor_login_completed",
            "user_id": user.pk,
        },
    )

    messages.success(
        request,
        (
            f"مرحبًا بك، "
            f"{user.get_full_name() or user.username}."
        ),
    )

    next_url = pending.get(
        "next",
        "",
    )
    if not next_url:
        next_url = request.session.pop(
            "admin_user_create_next",
            "",
        )

    if (
        next_url
        and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={
                request.get_host()
            },
            require_https=(
                request.is_secure()
            ),
        )
    ):
        return redirect(
            next_url
        )

    return redirect(
        "dashboard:index"
    )


# ============================================================
# Registration
# ============================================================

def _registration_context(
    photo_form,
    form_data=None,
):
    return {
        "job_title_choices": (
            Employee.JobTitle.choices
        ),
        "operational_section_choices": (
            Employee.OperationalSection.choices
        ),
        "female_job_title_labels": (
            EmployeeForm
            .FEMALE_JOB_TITLE_LABELS
        ),
        "form_data": (
            form_data
        ),
        "photo_form": (
            photo_form
        ),
    }


def register_view(
    request,
):
    """
    إنشاء حساب مستخدم جديد وربطه بسجل موظف.
    """

    if request.user.is_authenticated:
        return redirect(
            "dashboard:index"
        )

    if not settings.ALLOW_PUBLIC_REGISTRATION:
        raise PermissionDenied(
            "التسجيل العام غير متاح."
        )

    photo_form = ProfilePhotoForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST":
        full_name = (
            request.POST.get(
                "full_name"
            )
            or ""
        ).strip()

        employee_number = (
            request.POST.get(
                "employee_number"
            )
            or ""
        ).strip()

        username = (
            request.POST.get(
                "username"
            )
            or ""
        ).strip().lower()

        password = (
            request.POST.get(
                "password"
            )
            or ""
        )

        email = (
            request.POST.get(
                "email"
            )
            or ""
        ).strip().lower()

        phone_number = (
            request.POST.get(
                "phone_number"
            )
            or ""
        ).strip()

        operational_section = (
            request.POST.get(
                "operational_section"
            )
            or ""
        ).strip()

        job_title = (
            request.POST.get(
                "job_title"
            )
            or ""
        ).strip()

        context = (
            _registration_context(
                photo_form,
                request.POST,
            )
        )

        if not all(
            [
                full_name,
                employee_number,
                username,
                password,
                operational_section,
                job_title,
                email,
                phone_number,
            ]
        ):
            messages.error(
                request,
                "أكمل جميع الحقول المطلوبة.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        try:
            validate_email(email)
        except ValidationError:
            messages.error(
                request,
                "البريد الإلكتروني غير صالح.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        try:
            normalized_phone = normalize_saudi_phone_number(
                phone_number
            )
        except OTPRecipientValidationError:
            messages.error(
                request,
                "رقم الجوال غير صالح. استخدم رقمًا سعوديًا صحيحًا مثل +9665XXXXXXXX.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if (
            operational_section
            not in Employee.OperationalSection.values
        ):
            messages.error(
                request,
                (
                    "اختر القسم التشغيلي: "
                    "رجالي أو نسائي."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if (
            job_title
            not in Employee.JobTitle.values
        ):
            messages.error(
                request,
                (
                    "المسمى الوظيفي "
                    "المحدد غير صالح."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        try:
            validate_password(
                password,
                user=User(
                    username=username
                ),
            )

        except ValidationError as error:
            for message in error.messages:
                messages.error(
                    request,
                    message,
                )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if not photo_form.is_valid():
            messages.error(
                request,
                (
                    "تعذر رفع الصورة. "
                    "راجع الصيغة والحجم."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if User.objects.filter(
            username=username
        ).exists():
            messages.error(
                request,
                (
                    "اسم المستخدم "
                    "مستخدم مسبقًا."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if User.objects.filter(
            email__iexact=email
        ).exists():
            messages.error(
                request,
                "البريد الإلكتروني مستخدم مسبقًا.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if (
            Employee.objects.filter(
                phone_number=normalized_phone
            ).exists()
            or AccountProfile.objects.filter(
                phone_number=normalized_phone
            ).exists()
        ):
            messages.error(
                request,
                "رقم الجوال مستخدم مسبقًا.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        if Employee.objects.filter(
            employee_number=employee_number
        ).exists():
            messages.error(
                request,
                (
                    "الرقم الوظيفي "
                    "مسجل مسبقًا."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        try:
            with transaction.atomic():
                name_parts = (
                    full_name.split(
                        maxsplit=1
                    )
                )

                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    first_name=(
                        name_parts[0]
                    ),
                    last_name=(
                        name_parts[1]
                        if len(name_parts) > 1
                        else ""
                    ),
                )

                Employee.objects.create(
                    user=user,
                    full_name=full_name,
                    employee_number=(
                        employee_number
                    ),
                    operational_section=operational_section,
                    job_title=job_title,
                    phone_number=normalized_phone,
                    email=email,
                )

                AccountProfile.objects.create(
                    user=user,
                    phone_number=normalized_phone,
                    photo=(
                        photo_form
                        .cleaned_data
                        .get(
                            "photo"
                        )
                    ),
                )

                if not is_user_2fa_ready(user):
                    raise ValidationError("لا توجد قناة تحقق ثنائي متاحة للحساب.")

        except IntegrityError:
            messages.error(
                request,
                "تعذر إنشاء الحساب لأن بعض البيانات مستخدمة مسبقًا.",
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        except Exception:
            messages.error(
                request,
                (
                    "حدث خطأ غير متوقع "
                    "أثناء إنشاء الحساب."
                ),
            )

            return render(
                request,
                "accounts/register.html",
                context,
            )

        messages.success(
            request,
            (
                "تم إنشاء الحساب بنجاح، "
                "يمكنك تسجيل الدخول الآن."
            ),
        )

        return redirect(
            "accounts:login"
        )

    return render(
        request,
        "accounts/register.html",
        _registration_context(
            photo_form
        ),
    )


@login_required
def admin_user_create_view(request):
    """Endpoint إداري موحد لإنشاء الحسابات للأدوار المصرح لها فقط."""
    if not request.user.is_active:
        raise PermissionDenied("حساب المستخدم غير نشط.")

    if not request.user.has_perm("roles.manage_users"):
        raise PermissionDenied("ليس لديك صلاحية إدارة المستخدمين.")

    if requires_two_factor(request.user) and not has_completed_two_factor(request, request.user):
        request.session["admin_user_create_next"] = request.get_full_path()
        request.session.modified = True
        return redirect("accounts:two-factor")

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        employee_number = (request.POST.get("employee_number") or "").strip()
        username = (request.POST.get("username") or "").strip().lower()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        operational_section = (request.POST.get("operational_section") or "").strip()
        job_title = (request.POST.get("job_title") or "").strip()
        role_code = (request.POST.get("role") or "").strip().lower()
        phone_number = (request.POST.get("phone_number") or "").strip()

        if not all([full_name, employee_number, username, email, password, operational_section, job_title, role_code, phone_number]):
            messages.error(request, "أكمل جميع الحقول المطلوبة.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if operational_section not in Employee.OperationalSection.values:
            raise PermissionDenied("القسم التشغيلي غير صالح.")

        if job_title not in Employee.JobTitle.values:
            raise PermissionDenied("المسمى الوظيفي غير صالح.")

        allowed_sections = get_allowed_sections(request.user)
        if not allowed_sections:
            raise PermissionDenied("ليس لديك صلاحية لإدارة أي قسم تشغيلي.")
        if operational_section not in allowed_sections:
            raise PermissionDenied("لا يسمح لك إنشاء مستخدم خارج نطاق قسمك التشغيلي.")

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "البريد الإلكتروني غير صالح.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        try:
            normalized_phone = normalize_saudi_phone_number(phone_number)
        except OTPRecipientValidationError:
            messages.error(request, "رقم الجوال غير صالح. استخدم رقمًا سعوديًا صحيحًا مثل +9665XXXXXXXX.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        try:
            validate_password(password, user=User(username=username))
        except ValidationError as error:
            for message_text in error.messages:
                messages.error(request, message_text)
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "اسم المستخدم مستخدم مسبقًا.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "البريد الإلكتروني مستخدم مسبقًا.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if Employee.objects.filter(employee_number=employee_number).exists():
            messages.error(request, "الرقم الوظيفي مستخدم مسبقًا.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if Employee.objects.filter(phone_number=normalized_phone).exists() or AccountProfile.objects.filter(phone_number=normalized_phone).exists():
            messages.error(request, "رقم الجوال مستخدم مسبقًا.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        role = Role.objects.filter(code=role_code, is_active=True).first()
        if not role:
            messages.error(request, "الدور المحدد غير موجود أو غير نشط.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        if not user_has_permission(request.user, "roles.manage_users"):
            raise PermissionDenied("ليس لديك صلاحية إدارة المستخدمين.")

        if role.operational_section != Role.OperationalSection.ALL and operational_section not in {role.operational_section}:
            raise PermissionDenied("لا يمكن إنشاء مستخدم في قسم لا يندرج ضمن نطاق الدور المحدد.")

        try:
            with transaction.atomic():
                name_parts = full_name.split(maxsplit=1)
                new_user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    first_name=name_parts[0],
                    last_name=name_parts[1] if len(name_parts) > 1 else "",
                    is_staff=False,
                    is_superuser=False,
                )
                Employee.objects.create(
                    user=new_user,
                    full_name=full_name,
                    employee_number=employee_number,
                    operational_section=operational_section,
                    job_title=job_title,
                    phone_number=normalized_phone,
                    email=email,
                )
                AccountProfile.objects.create(user=new_user, phone_number=normalized_phone)
                assign_role_to_user(user=new_user, role_code=role.code)
        except IntegrityError:
            messages.error(request, "تعذر إنشاء الحساب لأن بعض البيانات مستخدمة مسبقًا.")
            return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "form_data": request.POST, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})

        messages.success(request, f"تم إنشاء الحساب بنجاح: {new_user.username}")
        return redirect("accounts:admin-user-create")

    return render(request, "accounts/admin_user_create.html", {"is_admin_create": True, "job_title_choices": Employee.JobTitle.choices, "role_options": Role.objects.filter(is_active=True).order_by("name")})


# ============================================================
# Login
# ============================================================

def login_view(
    request,
):
    """
    تسجيل الدخول.

    المستخدم المشمول بالـ2FA لا يحصل
    على جلسة دخول نهائية قبل نجاح OTP.
    """

    if request.user.is_authenticated:
        return redirect(
            "dashboard:index"
        )

    if request.method == "POST":
        username = (
            request.POST.get(
                "username"
            )
            or ""
        ).strip().lower()

        password = (
            request.POST.get(
                "password"
            )
            or ""
        )

        next_url = (
            request.POST.get(
                "next"
            )
            or ""
        )

        login_context = {
            "next": next_url,
            "entered_username": username,
        }

        if (
            not username
            or not password
        ):
            messages.error(
                request,
                (
                    "يرجى إدخال اسم المستخدم "
                    "وكلمة المرور."
                ),
            )

            return render(
                request,
                "accounts/login.html",
                login_context,
            )

        if login_is_limited(
            request,
            username,
        ):
            security_logger.warning(
                "Login attempt rate limited.",
                extra={
                    "event": (
                        "login_rate_limited"
                    ),
                },
            )

            messages.error(
                request,
                (
                    "تم تعليق محاولات الدخول "
                    "مؤقتًا. حاول لاحقًا."
                ),
            )

            return render(
                request,
                "accounts/login.html",
                login_context,
                status=429,
            )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            record_login_failure(
                request,
                username,
            )

            security_logger.warning(
                "Invalid login attempt.",
                extra={
                    "event": (
                        "login_failed"
                    ),
                },
            )

            messages.error(
                request,
                "بيانات الدخول غير صحيحة.",
            )

            return render(
                request,
                "accounts/login.html",
                login_context,
            )

        if not user.is_active:
            messages.error(
                request,
                "هذا الحساب معطل.",
            )

            return render(
                request,
                "accounts/login.html",
                login_context,
            )

        requires_two_factor = (
            _requires_two_factor(
                user
            )
        )

        if requires_two_factor:
            record_2fa_event(
                user=user,
                event="2fa_required",
                request=request,
                metadata={"policy_source": "login"},
            )

        security_logger.info(
            "Login credentials accepted.",
            extra={
                "event": (
                    "login_credentials_valid"
                ),
                "user_id": user.pk,
                "two_factor_required": (
                    requires_two_factor
                ),
            },
        )

        # ====================================================
        # Two-Factor
        # ====================================================

        if requires_two_factor:
            channels = (
                _employee_otp_channels(
                    user
                )
            )

            security_logger.info(
                (
                    "Two-factor channel "
                    "availability evaluated."
                ),
                extra={
                    "event": (
                        "two_factor_channels_checked"
                    ),
                    "user_id": user.pk,
                    "channel_count": (
                        len(channels)
                    ),
                },
            )

            if not channels:
                messages.error(
                    request,
                    (
                        "تعذر إتمام التحقق "
                        "الإضافي لهذا الحساب."
                    ),
                )

                return render(
                    request,
                    "accounts/login.html",
                    login_context,
                )

            pending = {
                "user_id": (
                    user.pk
                ),
                "created_at": time.time(),
                "next": (
                    next_url
                ),
                "remember_me": (
                    request.POST.get(
                        "remember_me"
                    )
                    == "on"
                ),
            }

            try:
                preferred_channel = (
                    _preferred_otp_channel(
                        user,
                        channels,
                    )
                )

                _request_login_otp(
                    user,
                    pending,
                    preferred_channel,
                )

            except OTPRateLimitedError:
                record_2fa_event(user=user, event="2fa_rate_limited", request=request)
                messages.error(
                    request,
                    (
                        "تعذر إرسال رمز "
                        "التحقق الآن. حاول لاحقًا."
                    ),
                )

                return render(
                    request,
                    "accounts/login.html",
                    login_context,
                    status=429,
                )

            except (
                VerificationNotConfiguredError,
                ProviderAuthenticationError,
                ProviderConnectionError,
                ProviderResponseError,
            ):
                security_logger.warning(
                    (
                        "Two-factor "
                        "initialization failed."
                    ),
                    extra={
                        "event": (
                            "two_factor_init_failed"
                        ),
                        "user_id": (
                            user.pk
                        ),
                    },
                )

                messages.error(
                    request,
                    (
                        "تعذر إتمام التحقق "
                        "الإضافي لهذا الحساب."
                    ),
                )

                return render(
                    request,
                    "accounts/login.html",
                    login_context,
                )

            request.session[
                TWO_FACTOR_SESSION_KEY
            ] = pending

            request.session.modified = True

            clear_login_failures(
                request,
                username,
            )

            security_logger.info(
                (
                    "User redirected to "
                    "two-factor verification."
                ),
                extra={
                    "event": (
                        "two_factor_pending"
                    ),
                    "user_id": (
                        user.pk
                    ),
                    "channel": (
                        pending.get(
                            "channel"
                        )
                    ),
                },
            )

            return redirect(
                "accounts:two-factor"
            )

        # ====================================================
        # Normal Login
        # ====================================================

        login(
            request,
            user,
        )

        clear_login_failures(
            request,
            username,
        )

        security_logger.info(
            (
                "User authenticated "
                "without two-factor."
            ),
            extra={
                "event": (
                    "login_succeeded"
                ),
                "user_id": (
                    user.pk
                ),
            },
        )

        if (
            request.POST.get(
                "remember_me"
            )
            == "on"
        ):
            request.session.set_expiry(
                60 * 60 * 24 * 30
            )

        else:
            request.session.set_expiry(
                0
            )

        messages.success(
            request,
            (
                f"مرحبًا بك، "
                f"{user.get_full_name() or user.username}."
            ),
        )

        if (
            next_url
            and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={
                    request.get_host()
                },
                require_https=(
                    request.is_secure()
                ),
            )
        ):
            return redirect(
                next_url
            )

        return redirect(
            "dashboard:index"
        )

    return render(
        request,
        "accounts/login.html",
        {
            "next": (
                request.GET.get(
                    "next",
                    "",
                )
            ),
        },
    )


# ============================================================
# Two Factor View
# ============================================================

def two_factor_view(
    request,
):
    """
    تغيير قناة / إعادة إرسال / Verify OTP.
    """

    if request.user.is_authenticated:
        return redirect(
            "dashboard:index"
        )

    user, pending = (
        _pending_two_factor(
            request
        )
    )

    if not user:
        messages.error(
            request,
            (
                "انتهت جلسة التحقق. "
                "سجّل الدخول مرة أخرى."
            ),
        )

        return redirect(
            "accounts:login"
        )

    if request.method == "POST":
        action = (
            request.POST.get(
                "action"
            )
            or ""
        ).strip()

        channel = (
            request.POST.get(
                "channel"
            )
            or pending.get(
                "channel"
            )
            or ""
        ).strip().lower()

        context = (
            _two_factor_context(
                user,
                pending,
            )
        )

        verification = context[
            "verification"
        ]

        try:
            # ------------------------------------------------
            # Change channel
            # ------------------------------------------------

            if action == "change-channel":
                _request_login_otp(
                    user,
                    pending,
                    channel,
                )

                request.session[
                    TWO_FACTOR_SESSION_KEY
                ] = pending

                request.session.modified = True

                record_2fa_event(
                    user=user,
                    event="2fa_channel_changed",
                    channel=channel,
                    request=request,
                    metadata={"verification_id": pending.get("verification_id")},
                )

                messages.success(
                    request,
                    (
                        "تم إرسال رمز "
                        "تحقق جديد."
                    ),
                )

                return redirect(
                    "accounts:two-factor"
                )

            # ------------------------------------------------
            # Resend
            # ------------------------------------------------

            if action == "resend":
                if not verification:
                    raise VerificationNotConfiguredError(
                        "لا يوجد طلب تحقق نشط."
                    )

                recipient = (
                    _otp_recipient(
                        user,
                        verification.channel,
                    )
                )

                if not recipient:
                    raise VerificationNotConfiguredError(
                        (
                            "بيانات قناة OTP "
                            "غير مكتملة."
                        )
                    )

                security_logger.info(
                    "Two-factor verification started.",
                    extra={
                        "event": "two_factor_verify_started",
                        "user_id": user.pk,
                        "channel": verification.channel,
                    },
                )

                record_2fa_event(
                    user=user,
                    event="2fa_resend_requested",
                    channel=verification.channel,
                    request=request,
                    metadata={"verification_id": verification.pk},
                )

                verification = (
                    AuthenticaOTPService(
                        get_provider()
                    )
                    .resend_otp(
                        verification=verification,
                        recipient=recipient,
                    )
                )

                pending[
                    "verification_id"
                ] = verification.pk

                request.session[
                    TWO_FACTOR_SESSION_KEY
                ] = pending

                request.session.modified = True

                messages.success(
                    request,
                    (
                        "تم إرسال رمز "
                        "تحقق جديد."
                    ),
                )

                return redirect(
                    "accounts:two-factor"
                )

            # ------------------------------------------------
            # Verify
            # ------------------------------------------------

            if action == "verify":
                if not verification:
                    raise VerificationNotConfiguredError(
                        "طلب التحقق غير صالح."
                    )

                otp = (
                    request.POST.get(
                        "otp"
                    )
                    or ""
                ).strip()

                if not otp:
                    messages.error(
                        request,
                        "رمز التحقق مطلوب.",
                    )

                    return render(
                        request,
                        "accounts/two_factor.html",
                        _two_factor_context(
                            user,
                            pending,
                        ),
                    )

                recipient = (
                    _otp_recipient(
                        user,
                        verification.channel,
                    )
                )

                if not recipient:
                    raise VerificationNotConfiguredError(
                        (
                            "بيانات قناة OTP "
                            "غير مكتملة."
                        )
                    )

                record_2fa_event(
                    user=user,
                    event="2fa_verify_started",
                    channel=verification.channel,
                    request=request,
                    metadata={"verification_id": verification.pk},
                )

                verification = (
                    AuthenticaOTPService(
                        get_provider()
                    )
                    .verify_otp(
                        verification=verification,
                        otp=otp,
                        recipient=recipient,
                    )
                )

                if (
                    verification.status
                    == OTPVerification
                    .Status
                    .VERIFIED
                ):
                    security_logger.info(
                        (
                            "User completed "
                            "two-factor authentication."
                        ),
                        extra={
                            "event": (
                                "two_factor_succeeded"
                            ),
                            "user_id": (
                                user.pk
                            ),
                        },
                    )

                    return _complete_login(
                        request,
                        user,
                        pending,
                    )

                security_logger.warning(
                    (
                        "Two-factor "
                        "verification failed."
                    ),
                    extra={
                        "event": (
                            "two_factor_failed"
                        ),
                        "user_id": (
                            user.pk
                        ),
                    },
                )

                messages.error(
                    request,
                    (
                        "رمز التحقق غير صالح "
                        "أو انتهت صلاحيته."
                    ),
                )

            else:
                raise VerificationNotConfiguredError(
                    "طلب التحقق غير صالح."
                )

        except OTPResendCooldownError:
            messages.error(
                request,
                (
                    "إعادة الإرسال غير متاحة "
                    "بعد. حاول لاحقًا."
                ),
            )

        except OTPRateLimitedError:
            record_2fa_event(user=user, event="2fa_rate_limited", request=request)
            messages.error(
                request,
                (
                    "تعذر إرسال رمز "
                    "التحقق الآن. حاول لاحقًا."
                ),
            )

        except VerificationNotConfiguredError:
            messages.error(
                request,
                (
                    "تعذر إتمام التحقق "
                    "الإضافي. حاول لاحقًا."
                ),
            )

        except (
            ProviderAuthenticationError,
            ProviderConnectionError,
            ProviderResponseError,
        ):
            security_logger.warning(
                (
                    "Authentica two-factor "
                    "provider error."
                ),
                extra={
                    "event": (
                        "two_factor_provider_error"
                    ),
                    "user_id": (
                        user.pk
                    ),
                },
            )

            messages.error(
                request,
                (
                    "تعذر إتمام التحقق "
                    "الإضافي. حاول لاحقًا."
                ),
            )

    return render(
        request,
        "accounts/two_factor.html",
        _two_factor_context(
            user,
            pending,
        ),
    )


# ============================================================
# Logout
# ============================================================

@require_POST
@login_required
def logout_view(
    request,
):
    """
    تسجيل خروج المستخدم بطريقة آمنة عبر POST.
    """

    username = (
        request.user.get_full_name()
        or request.user.username
    )

    user_id = (
        request.user.pk
    )

    request.session.pop(
        TWO_FACTOR_SESSION_KEY,
        None,
    )

    clear_two_factor_verification(
        request
    )

    auth_logout(
        request
    )

    security_logger.info(
        "User signed out.",
        extra={
            "event": "logout",
            "user_id": user_id,
        },
    )

    messages.success(
        request,
        (
            f"تم تسجيل خروج "
            f"{username} بنجاح."
        ),
    )

    return redirect(
        "accounts:login"
    )


# ============================================================
# Profile
# ============================================================

@login_required
def profile_view(
    request,
):
    """
    عرض وتحديث الملف الشخصي.

    يدعم:
    - الصورة الشخصية
    - رقم الجوال
    """

    user = request.user

    account_profile, _ = (
        AccountProfile.objects
        .get_or_create(
            user=user,
        )
    )

    employee = (
        Employee.objects
        .filter(
            user=user
        )
        .first()
    )

    if request.method == "POST":
        form_type = (
            request.POST.get(
                "form_type"
            )
            or "photo"
        ).strip().lower()

        # ====================================================
        # Contact Form
        # ====================================================

        if form_type == "contact":
            contact_form = (
                ProfileContactForm(
                    request.POST,
                    instance=account_profile,
                )
            )

            photo_form = (
                ProfilePhotoForm(
                    instance=account_profile,
                )
            )

            if contact_form.is_valid():
                if contact_form.cleaned_data["phone_number"] != account_profile.phone_number:
                    messages.error(
                        request,
                        "تغيير رقم الجوال يتطلب تحققًا من الرقم الجديد ولا يمكن حفظه مباشرة.",
                    )
                else:
                    return redirect("accounts:profile")

            messages.error(
                request,
                (
                    "تعذر تحديث رقم الجوال. "
                    "راجع الرقم المدخل."
                ),
            )

        # ====================================================
        # Photo Form
        # ====================================================

        else:
            photo_form = (
                ProfilePhotoForm(
                    request.POST,
                    request.FILES,
                    instance=account_profile,
                )
            )

            contact_form = (
                ProfileContactForm(
                    instance=account_profile,
                )
            )

            if photo_form.is_valid():
                photo_form.save()

                messages.success(
                    request,
                    (
                        "تم تحديث الصورة "
                        "الشخصية بنجاح."
                    ),
                )

                return redirect(
                    "accounts:profile"
                )

            messages.error(
                request,
                (
                    "تعذر تحديث الصورة. "
                    "راجع الصيغة والحجم."
                ),
            )

    else:
        photo_form = (
            ProfilePhotoForm(
                instance=account_profile,
            )
        )

        contact_form = (
            ProfileContactForm(
                instance=account_profile,
            )
        )

    if user.is_superuser:
        account_role = (
            "مدير النظام"
        )

    elif user.is_staff:
        account_role = (
            "موظف إداري"
        )

    elif (
        employee
        and getattr(
            employee,
            "job_title",
            None,
        )
    ):
        try:
            account_role = (
                employee
                .get_job_title_display()
            )

        except (
            AttributeError,
            TypeError,
        ):
            account_role = (
                "مستخدم"
            )

    else:
        account_role = (
            "مستخدم"
        )

    full_name = (
        employee.full_name
        if (
            employee
            and employee.full_name
        )
        else (
            user.get_full_name()
            or user.username
        )
    )

    effective_phone = (
        _account_phone_number(
            user
        )
    )

    context = {
        "profile_user": (
            user
        ),
        "employee": (
            employee
        ),
        "full_name": (
            full_name
        ),
        "account_role": (
            account_role
        ),
        "account_profile": (
            account_profile
        ),
        "photo_form": (
            photo_form
        ),
        "contact_form": (
            contact_form
        ),
        "effective_phone": (
            effective_phone
        ),
    }

    return render(
        request,
        "accounts/profile.html",
        context,
    )


# ============================================================
# Change Password
# ============================================================

@login_required
def password_change_view(
    request,
):
    """
    تغيير كلمة مرور المستخدم الحالي
    مع الإبقاء على جلسة الدخول.
    """

    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST,
        )

        if form.is_valid():
            user = form.save()

            update_session_auth_hash(
                request,
                user,
            )

            messages.success(
                request,
                (
                    "تم تغيير كلمة "
                    "المرور بنجاح."
                ),
            )

            return redirect(
                "accounts:profile"
            )

        messages.error(
            request,
            (
                "تعذر تغيير كلمة المرور. "
                "راجع البيانات المدخلة."
            ),
        )

    else:
        form = PasswordChangeForm(
            user=request.user,
        )

    return render(
        request,
        "accounts/password_change.html",
        {
            "form": form,
        },
    )
