from __future__ import annotations

from django.core.exceptions import PermissionDenied


def require_staff(user):
    """
    السماح فقط للمستخدمين من طاقم الإدارة.
    """

    if not user or not user.is_authenticated:
        raise PermissionDenied("يجب تسجيل الدخول أولًا")

    if not user.is_staff:
        raise PermissionDenied("غير مصرح لك")


def require_permission(user, permission_code: str):
    """
    التحقق من صلاحية Django Permission.
    مثال:
    reporting.can_approve_shift_report
    """

    require_staff(user)

    if not user.has_perm(permission_code):
        raise PermissionDenied("لا تملك الصلاحية المطلوبة")


def has_employee_profile(user) -> bool:
    """
    هل المستخدم مرتبط بملف موظف؟
    """

    return (
        user
        and user.is_authenticated
        and hasattr(user, "employee")
        and user.employee is not None
    )


def get_employee(user):
    """
    إرجاع ملف الموظف المرتبط بالمستخدم.
    """

    if not has_employee_profile(user):
        return None

    return user.employee


def require_employee_profile(user):
    """
    اشتراط وجود ملف موظف مرتبط بالمستخدم.
    """

    employee = get_employee(user)

    if not employee:
        raise PermissionDenied("لا يوجد ملف موظف مرتبط بحسابك")

    return employee


def require_job_title(user, allowed_titles: list[str]):
    """
    السماح حسب المسمى الوظيفي.
    """

    employee = require_employee_profile(user)

    if employee.job_title not in allowed_titles:
        raise PermissionDenied("غير مصرح لك حسب المسمى الوظيفي")

    return employee


def require_any_role(user, allowed_titles: list[str]):
    """
    اسم بديل أوضح للاستخدام في Views.
    """

    return require_job_title(user, allowed_titles)


def require_general_manager(user):
    """
    المدير العام فقط.
    """

    from apps.hr.models import Employee

    return require_job_title(
        user,
        [
            Employee.JobTitle.GM,
        ],
    )


def require_doors_management(user):
    """
    إدارة قسم الأبواب.
    """

    from apps.hr.models import Employee

    return require_job_title(
        user,
        [
            Employee.JobTitle.GM,
            Employee.JobTitle.DOORS_HEAD,
            Employee.JobTitle.DOORS_DEPUTY,
            Employee.JobTitle.SENIOR_ADMIN,
        ],
    )


def require_shift_supervisor(user):
    """
    مشرفو الورديات.
    """

    from apps.hr.models import Employee

    return require_job_title(
        user,
        [
            Employee.JobTitle.FAJR_SUPERVISOR,
            Employee.JobTitle.DUHA_SUPERVISOR,
            Employee.JobTitle.EVENING_SUPERVISOR,
            Employee.JobTitle.SUPPORT_SUPERVISOR,
        ],
    )


def require_shift_leadership(user):
    """
    مشرفو الورديات ونوابهم.
    """

    from apps.hr.models import Employee

    return require_job_title(
        user,
        [
            Employee.JobTitle.FAJR_SUPERVISOR,
            Employee.JobTitle.DUHA_SUPERVISOR,
            Employee.JobTitle.EVENING_SUPERVISOR,
            Employee.JobTitle.SUPPORT_SUPERVISOR,
            Employee.JobTitle.FAJR_DEPUTY,
            Employee.JobTitle.DUHA_DEPUTY,
            Employee.JobTitle.EVENING_DEPUTY,
        ],
    )


def require_maintenance_member(user):
    """
    فريق الصيانة.
    """

    employee = require_employee_profile(user)

    if not employee.can_execute_maintenance:
        raise PermissionDenied("هذه الصفحة مخصصة لفريق الصيانة")

    return employee


def require_admin_office(user):
    """
    الفريق الإداري والسكرتارية.
    """

    from apps.hr.models import Employee

    return require_job_title(
        user,
        [
            Employee.JobTitle.GM,
            Employee.JobTitle.DOORS_HEAD,
            Employee.JobTitle.DOORS_DEPUTY,
            Employee.JobTitle.SENIOR_ADMIN,
            Employee.JobTitle.ADMIN_SECRETARY,
            Employee.JobTitle.TECH_SECRETARY,
        ],
    )