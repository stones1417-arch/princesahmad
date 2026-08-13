from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.hr.models import Employee
from apps.roles.services.role_manager import assign_role_to_user

from ..models import AccountProfile, AccountRegistrationRequest

User = get_user_model()


def _full_name_parts(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _expected_operational_section(gender: str) -> str:
    if gender == AccountRegistrationRequest.Gender.FEMALE:
        return Employee.OperationalSection.FEMALE
    return Employee.OperationalSection.MALE


@transaction.atomic
def approve_account_registration_request(
    registration_request: AccountRegistrationRequest,
    *,
    reviewer=None,
) -> User:
    """Create the actual user and employee from an approved registration request."""
    if not isinstance(registration_request, AccountRegistrationRequest):
        raise TypeError("registration_request must be an AccountRegistrationRequest instance.")

    if registration_request.status == AccountRegistrationRequest.Status.APPROVED and registration_request.created_user_id:
        return registration_request.created_user

    if registration_request.status not in {
        AccountRegistrationRequest.Status.PENDING,
        AccountRegistrationRequest.Status.NEEDS_EDIT,
    }:
        if registration_request.status == AccountRegistrationRequest.Status.REJECTED:
            raise ValidationError("لا يمكن اعتماد طلب تم رفضه مسبقًا.")
        if registration_request.status == AccountRegistrationRequest.Status.CANCELLED:
            raise ValidationError("لا يمكن اعتماد طلب تم إلغاؤه.")
        raise ValidationError("لا يمكن اعتماد طلب غير مفتوح للمراجعة.")

    if registration_request.gender not in AccountRegistrationRequest.Gender.values:
        raise ValidationError("الجنس المحدد غير صالح.")

    expected_section = _expected_operational_section(registration_request.gender)

    if registration_request.created_user_id:
        user = registration_request.created_user
    else:
        username = registration_request.requested_username.strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("اسم المستخدم مستخدم مسبقًا.")

        if User.objects.filter(email__iexact=registration_request.email).exists():
            raise ValidationError("البريد الإلكتروني مستخدم مسبقًا.")

        first_name, last_name = _full_name_parts(registration_request.full_name)
        user = User.objects.create(
            username=username,
            email=registration_request.email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

    if User.objects.filter(email__iexact=registration_request.email).exclude(pk=user.pk).exists():
        raise ValidationError("البريد الإلكتروني مستخدم مسبقًا.")

    if Employee.objects.filter(employee_number=registration_request.employee_number).exclude(user=user).exists():
        raise ValidationError("الرقم الوظيفي مسجل مسبقًا.")

    if Employee.objects.filter(phone_number=registration_request.phone_number).exclude(user=user).exists():
        raise ValidationError("رقم الجوال مستخدم مسبقًا.")

    if AccountProfile.objects.filter(phone_number=registration_request.phone_number).exclude(user=user).exists():
        raise ValidationError("رقم الجوال مستخدم مسبقًا.")

    employee = getattr(user, "employee", None)

    if employee is None:
        employee = Employee.objects.create(
            user=user,
            full_name=registration_request.full_name,
            employee_number=registration_request.employee_number,
            operational_section=expected_section,
            job_title=Employee.JobTitle.MONITOR,
            phone_number=registration_request.phone_number,
            email=registration_request.email,
        )
    else:
        employee.full_name = registration_request.full_name
        employee.employee_number = registration_request.employee_number
        employee.operational_section = expected_section
        employee.job_title = Employee.JobTitle.MONITOR
        employee.phone_number = registration_request.phone_number
        employee.email = registration_request.email
        employee.save()

    AccountProfile.objects.update_or_create(
        user=user,
        defaults={
            "phone_number": registration_request.phone_number,
        },
    )

    assign_role_to_user(user=user, role_code="employee")

    registration_request.status = AccountRegistrationRequest.Status.APPROVED
    registration_request.reviewed_by = reviewer
    registration_request.reviewed_at = timezone.now()
    registration_request.created_user = user
    registration_request.linked_employee = employee
    registration_request.save(update_fields=[
        "status",
        "reviewed_by",
        "reviewed_at",
        "created_user",
        "linked_employee",
        "updated_at",
    ])

    return user
