from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import BooleanField, Case, Q, QuerySet, Value, When
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.dashboard.models import SystemActivityLog
from apps.hr.models import Employee
from apps.roles.models import Role
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.role_manager import assign_role_to_user
from apps.roles.services.section_access import get_allowed_sections, has_institutional_scope

from ..models import AccountProfile, AccountRegistrationRequest

User = get_user_model()
logger = logging.getLogger(__name__)


AWAITING_ACTIVATION_Q = Q(
    status=AccountRegistrationRequest.Status.APPROVED,
    created_user__isnull=False,
) & (Q(activated_at__isnull=True) | Q(created_user__is_active=False))


def effective_request_section_q(section: str) -> Q:
    """Match the reviewed section, falling back to applicant gender for legacy rows."""
    return Q(operational_section=section) | (
        (Q(operational_section="") | Q(operational_section__isnull=True))
        & Q(gender=section)
    )


def scope_registration_requests_for_user(
    queryset: QuerySet,
    *,
    user,
    section: str,
) -> QuerySet:
    """Apply the effective UI section without allowing cross-section visibility."""
    allowed_sections = get_allowed_sections(user)
    if has_institutional_scope(user) and section not in allowed_sections:
        section = next(iter(allowed_sections)) if len(allowed_sections) == 1 else "all"

    if section in {Employee.OperationalSection.MALE, Employee.OperationalSection.FEMALE}:
        queryset = queryset.filter(effective_request_section_q(section))
    return queryset.annotate(
        is_awaiting_activation=Case(
            When(AWAITING_ACTIVATION_Q, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )


def _audit(actor, action, description):
    SystemActivityLog.objects.create(user=actor, module="طلبات إنشاء الحساب", action=action, description=description)


def get_approvable_roles(reviewer):
    roles = Role.objects.filter(is_active=True).order_by("name")
    if not user_has_permission(reviewer, PlatformPermissions.MANAGE_ROLES):
        roles = roles.exclude(code="system_admin")
    return roles


def verify_registration_request(registration_request):
    users = User.objects.filter(username__iexact=registration_request.requested_username) | User.objects.filter(email__iexact=registration_request.email)
    employees = Employee.objects.filter(employee_number=registration_request.employee_number)
    duplicate = AccountRegistrationRequest.objects.filter(
        employee_number=registration_request.employee_number,
        status__in=(AccountRegistrationRequest.Status.APPROVED, AccountRegistrationRequest.Status.ACTIVATED),
    ).exclude(pk=registration_request.pk)
    return {
        "username_available": not User.objects.filter(username__iexact=registration_request.requested_username).exists(),
        "email_available": not User.objects.filter(email__iexact=registration_request.email).exists(),
        "employee_available": not employees.exists(),
        "approved_request_available": not duplicate.exists(),
        "existing_user": users.first(),
        "existing_employee": employees.first(),
    }


def _validate_role_and_section(*, reviewer, role_code, section):
    try:
        role = get_approvable_roles(reviewer).get(code=role_code)
    except Role.DoesNotExist as exc:
        raise PermissionDenied("الدور المحدد غير مسموح في اعتماد الحسابات.") from exc
    if section not in Employee.OperationalSection.values:
        raise ValidationError("القسم التشغيلي غير صالح.")
    if role.operational_section not in (Role.OperationalSection.ALL, section):
        raise ValidationError("الدور المحدد لا يطابق القسم التشغيلي.")
    return role


def _activation_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:activate", args=[uid, token])
    return f"{getattr(settings, 'SITE_URL', 'http://localhost').rstrip('/')}{path}"


def send_activation_email(registration_request_id):
    registration = AccountRegistrationRequest.objects.select_related("created_user").get(pk=registration_request_id)
    user = registration.created_user
    if not user or user.is_active or registration.status != AccountRegistrationRequest.Status.APPROVED:
        raise ValidationError("الحساب غير مؤهل لإرسال رابط التفعيل.")
    try:
        send_mail(
            "تفعيل حساب منصة أبواب",
            f"مرحبًا {registration.full_name}\nتم اعتماد طلب إنشاء حسابك في منصة أبواب.\n\nاسم المستخدم: {user.username}\n\nفعّل الحساب وحدد كلمة مرورك عبر الرابط:\n{_activation_url(user)}",
            getattr(settings, "DEFAULT_FROM_EMAIL", None), [registration.email], fail_silently=False,
        )
    except Exception as exc:
        AccountRegistrationRequest.objects.filter(pk=registration.pk).update(activation_email_error=str(exc)[:1000], activation_email_sent_at=None)
        logger.exception("Activation email failed for registration request %s", registration.pk)
        _audit(None, SystemActivityLog.ActionType.OTHER, f"فشل إرسال رابط تفعيل الطلب #{registration.pk}")
        return False
    AccountRegistrationRequest.objects.filter(pk=registration.pk).update(activation_email_sent_at=timezone.now(), activation_email_error="")
    _audit(None, SystemActivityLog.ActionType.OTHER, f"تم إرسال رابط تفعيل الطلب #{registration.pk}")
    return True


@transaction.atomic
def approve_account_registration_request(registration_request, *, reviewer=None, role_code="employee", operational_section=None):
    if not isinstance(registration_request, AccountRegistrationRequest):
        raise TypeError("registration_request must be an AccountRegistrationRequest instance.")
    locked = AccountRegistrationRequest.objects.select_for_update().get(pk=registration_request.pk)
    if locked.status in (locked.Status.APPROVED, locked.Status.ACTIVATED) and locked.created_user_id:
        return locked.created_user
    if locked.status not in (locked.Status.PENDING, locked.Status.NEEDS_EDIT):
        raise ValidationError("الطلب غير مفتوح للاعتماد.")
    if reviewer and (reviewer.username.lower() == locked.requested_username.lower() or (reviewer.email and reviewer.email.lower() == locked.email.lower())):
        raise PermissionDenied("لا يمكن اعتماد طلبك الشخصي.")
    section = operational_section or (Employee.OperationalSection.FEMALE if locked.gender == locked.Gender.FEMALE else Employee.OperationalSection.MALE)
    if section != locked.gender:
        raise ValidationError("القسم التشغيلي لا يطابق بيانات مقدم الطلب.")
    role = _validate_role_and_section(reviewer=reviewer, role_code=role_code, section=section)
    verification = verify_registration_request(locked)
    if not all(verification[key] for key in ("username_available", "email_available", "employee_available", "approved_request_available")):
        raise ValidationError("الحساب أو الموظف موجود بالفعل.")
    names = locked.full_name.strip().split(maxsplit=1)
    user = User(username=locked.requested_username.strip().lower(), email=locked.email.strip().lower(), first_name=names[0], last_name=names[1] if len(names) > 1 else "", is_active=False, is_staff=False, is_superuser=False)
    user.set_unusable_password()
    user.save()
    employee = Employee.objects.create(user=user, full_name=locked.full_name, employee_number=locked.employee_number, operational_section=section, job_title=Employee.JobTitle.MONITOR, phone_number=locked.phone_number, email=locked.email)
    AccountProfile.objects.update_or_create(user=user, defaults={"phone_number": locked.phone_number})
    assign_role_to_user(user=user, role_code=role.code, assigned_by=reviewer, notes=f"اعتماد طلب #{locked.pk}")
    locked.status = locked.Status.APPROVED
    locked.reviewed_by = reviewer
    locked.reviewed_at = timezone.now()
    locked.created_user = user
    locked.linked_employee = employee
    locked.approved_role = role
    locked.operational_section = section
    locked.rejection_reason = ""
    locked.save()
    _audit(reviewer, SystemActivityLog.ActionType.APPROVE, f"اعتماد الطلب #{locked.pk} وإنشاء المستخدم والموظف وإسناد الدور {role.code}")
    transaction.on_commit(lambda: send_activation_email(locked.pk))
    registration_request.refresh_from_db()
    return user


@transaction.atomic
def reject_registration_request(registration_request, *, reviewer, reason):
    locked = AccountRegistrationRequest.objects.select_for_update().get(pk=registration_request.pk)
    if locked.status not in (locked.Status.PENDING, locked.Status.NEEDS_EDIT):
        raise ValidationError("الطلب غير مفتوح للرفض.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("سبب الرفض مطلوب.")
    locked.status = locked.Status.REJECTED
    locked.reviewed_by = reviewer
    locked.reviewed_at = timezone.now()
    locked.rejection_reason = reason
    locked.review_notes = reason
    locked.save()
    _audit(reviewer, SystemActivityLog.ActionType.UPDATE, f"رفض الطلب #{locked.pk}: {reason}")
    return locked
