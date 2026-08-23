
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.hr.models import Employee
from apps.roles.models import Role
from apps.roles.services.access_control import (
    get_user_active_roles,
    user_has_permission,
)
from apps.roles.services.assignment_management import (
    assign_employee_role,
    remove_employee_role,
)
from apps.roles.services.permission_presentation import (
    permission_comparison,
    present_permission_codes,
    role_permission_codes,
)
from apps.roles.services.permission_registry import PlatformPermissions
from apps.roles.services.section_access import filter_employees_for_user


def _require_role_manager(user) -> None:
    if not user_has_permission(user, PlatformPermissions.MANAGE_ROLES):
        raise PermissionDenied("غير مصرح لك بإدارة تسكين الأدوار.")


@login_required
def employee_assignment_view(request):
    _require_role_manager(request.user)
    employees = filter_employees_for_user(
        Employee.objects.select_related("user").filter(user__isnull=False),
        request.user,
    )
    selectable_employees = employees
    if request.GET.get("include_inactive") != "1":
        employees = employees.filter(is_active=True, user__is_active=True)
    query = (request.GET.get("q") or "").strip()
    section = (request.GET.get("section") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    if query:
        employees = employees.filter(
            Q(full_name__icontains=query)
            | Q(employee_number__icontains=query)
            | Q(user__username__icontains=query)
        )
    if section in Employee.OperationalSection.values:
        employees = employees.filter(operational_section=section)
    if role_filter:
        employees = employees.filter(
            user__platform_role_assignments__role__code=role_filter,
            user__platform_role_assignments__is_active=True,
        )
    roles = list(
        Role.objects.filter(is_active=True)
        .select_related("group")
        .prefetch_related("group__permissions__content_type")
    )
    selected_employee = None
    selected_role = None
    comparison = None
    employee_id = request.POST.get("employee") or request.GET.get("employee")
    role_code = request.POST.get("role") or request.GET.get("selected_role")
    if employee_id:
        selected_employee = get_object_or_404(selectable_employees, pk=employee_id)
    if role_code:
        selected_role = get_object_or_404(Role.objects.select_related("group"), code=role_code, is_active=True)
    if selected_employee and selected_role:
        comparison = permission_comparison(selected_employee.user, selected_role)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "remove":
                remove_employee_role(
                    actor=request.user,
                    employee=selected_employee,
                    role=selected_role,
                )
            else:
                assign_employee_role(
                    actor=request.user,
                    employee=selected_employee,
                    role=selected_role,
                    section=(request.POST.get("section") or "").strip(),
                )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            if request.POST.get("action") == "remove":
                messages.success(request, f"تمت إزالة دور {selected_role.name} من {selected_employee.full_name}")
            else:
                messages.success(
                    request,
                    f"تم تسكين {selected_employee.full_name} كـ {selected_role.name} — {selected_employee.get_operational_section_display()}",
                )
            return redirect(f"{request.path}?employee={selected_employee.pk}&selected_role={selected_role.code}")
    role_cards = [
        {
            "role": role,
            "permission_count": len(role_permission_codes(role)),
            "permissions": present_permission_codes(role_permission_codes(role)),
        }
        for role in roles
    ]
    current_roles = list(get_user_active_roles(selected_employee.user)) if selected_employee else []
    return render(request, "roles/employee_assignment.html", {
        "employees": employees.distinct().order_by("full_name"),
        "role_cards": role_cards,
        "roles": roles,
        "selected_employee": selected_employee,
        "selected_role": selected_role,
        "current_roles": current_roles,
        "comparison": comparison,
        "sections": Employee.OperationalSection.choices,
        "query": query,
        "selected_section": section,
        "include_inactive": request.GET.get("include_inactive") == "1",
    })


@login_required
def role_detail_view(request, code):
    _require_role_manager(request.user)
    role = get_object_or_404(
        Role.objects.select_related("group").prefetch_related(
            "group__permissions__content_type",
            "user_assignments__user__employee",
        ),
        code=code,
        is_active=True,
    )
    permissions = present_permission_codes(role_permission_codes(role))
    assignees = role.user_assignments.filter(is_active=True).select_related("user", "user__employee")
    return render(request, "roles/role_detail.html", {
        "role": role,
        "permission_groups": permissions,
        "permission_count": sum(len(group["permissions"]) for group in permissions),
        "assignees": assignees,
    })
