from __future__ import annotations
from django.http import JsonResponse
from django.db import transaction
from openpyxl import Workbook
from openpyxl.styles import Font

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.permissions import require_staff

from .forms import EmployeeForm
from .models import Employee
from .services import EmployeeService


@login_required
def employee_list_view(request):
    require_staff(request.user)

    q = (request.GET.get("q") or "").strip()
    job_title = (request.GET.get("job_title") or "").strip()
    work_status = (request.GET.get("work_status") or "").strip()
    active_filter = (request.GET.get("active") or "").strip()

    employees = Employee.objects.select_related("user").all()

    if q:
        employees = employees.filter(
            Q(full_name__icontains=q)
            | Q(employee_number__icontains=q)
            | Q(phone_number__icontains=q)
            | Q(national_id__icontains=q)
            | Q(email__icontains=q)
            | Q(user__username__icontains=q)
        )

    if job_title:
        employees = employees.filter(job_title=job_title)

    if work_status:
        employees = employees.filter(work_status=work_status)

    if active_filter == "active":
        employees = employees.filter(is_active=True)
    elif active_filter == "inactive":
        employees = employees.filter(is_active=False)

    employees = employees.order_by("employee_number")
    all_employees = Employee.objects.all()

    context = {
        "employees": employees,
        "q": q,
        "selected_job_title": job_title,
        "selected_work_status": work_status,
        "selected_active": active_filter,
        "job_title_choices": Employee.JobTitle.choices,
        "work_status_choices": Employee.WorkStatus.choices,
        "total_employees": all_employees.count(),
        "active_employees": all_employees.filter(is_active=True).count(),
        "inactive_employees": all_employees.filter(is_active=False).count(),
        "maintenance_members": all_employees.filter(can_execute_maintenance=True).count(),
        "door_assignable_members": all_employees.filter(
            is_active=True,
            can_work_on_doors=True,
        ).count(),
        "job_title_stats": (
            all_employees
            .values("job_title")
            .annotate(total=Count("id"))
            .order_by("-total")
        ),
    }

    return render(request, "hr/employee_list.html", context)


@login_required
def employee_create_view(request):
    require_staff(request.user)

    if request.method == "POST":
        form = EmployeeForm(request.POST)

        if form.is_valid():
            try:
                employee = EmployeeService.create(
                    request=request,
                    form=form,
                )

                messages.success(
                    request,
                    f"تم إضافة الموظف {employee.full_name} بنجاح"
                )
                return redirect("hr:list")

            except IntegrityError:
                form.add_error("employee_number", "الرقم الوظيفي مستخدم مسبقًا")
                messages.error(request, "الرقم الوظيفي مستخدم مسبقًا")
        else:
            messages.error(request, "تحقق من الحقول المدخلة")
    else:
        form = EmployeeForm()

    return render(
        request,
        "hr/employee_form.html",
        {
            "title": "إضافة موظف",
            "form": form,
        }
    )


@login_required
def employee_update_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(Employee, pk=pk)

    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=employee)

        if form.is_valid():
            try:
                employee = EmployeeService.update(
                    request=request,
                    form=form,
                )

                messages.success(
                    request,
                    f"تم تحديث بيانات الموظف {employee.full_name}"
                )
                return redirect("hr:list")

            except IntegrityError:
                form.add_error("employee_number", "الرقم الوظيفي مستخدم مسبقًا")
                messages.error(request, "الرقم الوظيفي مستخدم مسبقًا")
        else:
            messages.error(request, "تحقق من الحقول المدخلة")
    else:
        form = EmployeeForm(instance=employee)

    return render(
        request,
        "hr/employee_form.html",
        {
            "title": "تعديل موظف",
            "form": form,
            "employee": employee,
        }
    )


@login_required
@require_POST
def employee_toggle_active_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(Employee, pk=pk)
    was_active = employee.is_active

    employee = EmployeeService.toggle_active(
        request=request,
        employee=employee,
    )

    if was_active:
        messages.warning(request, f"تم تعطيل الموظف {employee.full_name}")
    else:
        messages.success(request, f"تم تفعيل الموظف {employee.full_name}")

    return redirect("hr:list")


@login_required
def employee_delete_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(Employee, pk=pk)

    if request.method == "POST":
        employee = EmployeeService.safe_delete(
            request=request,
            employee=employee,
        )

        messages.warning(
            request,
            f"تم تعطيل الموظف {employee.full_name} بدل الحذف النهائي"
        )
        return redirect("hr:list")

    return render(
        request,
        "hr/employee_confirm_delete.html",
        {
            "employee": employee,
        }
    )


@login_required
def export_employees_excel(request):
    require_staff(request.user)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "سجل الموظفين"

    headers = [
        "الرقم الوظيفي",
        "الاسم الكامل",
        "رقم الهوية",
        "رقم الجوال",
        "البريد الإلكتروني",
        "المسمى الوظيفي",
        "حالة الموظف",
        "نشط في النظام",
        "يمكن تسكينه على الأبواب",
        "يمكنه تنفيذ الصيانة",
        "تاريخ المباشرة",
        "ملاحظات",
        "تاريخ الإضافة",
        "آخر تحديث",
    ]

    for col, title in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=col)
        cell.value = title
        cell.font = Font(bold=True)

    employees = Employee.objects.select_related("user").order_by("employee_number")

    for row, employee in enumerate(employees, start=2):
        sheet.cell(row=row, column=1).value = employee.employee_number
        sheet.cell(row=row, column=2).value = employee.full_name
        sheet.cell(row=row, column=3).value = employee.national_id
        sheet.cell(row=row, column=4).value = employee.phone_number
        sheet.cell(row=row, column=5).value = employee.email
        sheet.cell(row=row, column=6).value = employee.get_job_title_display()
        sheet.cell(row=row, column=7).value = employee.get_work_status_display()
        sheet.cell(row=row, column=8).value = "نعم" if employee.is_active else "لا"
        sheet.cell(row=row, column=9).value = "نعم" if employee.can_work_on_doors else "لا"
        sheet.cell(row=row, column=10).value = "نعم" if employee.can_execute_maintenance else "لا"
        sheet.cell(row=row, column=11).value = (
            employee.hire_date.strftime("%Y-%m-%d")
            if employee.hire_date
            else ""
        )
        sheet.cell(row=row, column=12).value = employee.notes
        sheet.cell(row=row, column=13).value = employee.created_at.strftime("%Y-%m-%d %H:%M")
        sheet.cell(row=row, column=14).value = employee.updated_at.strftime("%Y-%m-%d %H:%M")

    for column_cells in sheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter

        for cell in column_cells:
            value = str(cell.value) if cell.value is not None else ""
            max_length = max(max_length, len(value))

        sheet.column_dimensions[column_letter].width = min(max_length + 4, 35)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="employees.xlsx"'

    workbook.save(response)

    return response
@login_required
@require_POST
def employee_toggle_active_ajax_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(Employee, pk=pk)

    try:
        with transaction.atomic():

            employee = EmployeeService.toggle_active(
                request=request,
                employee=employee,
            )

            return JsonResponse({
                "success": True,
                "employee_id": employee.pk,
                "is_active": employee.is_active,
                "message":
                    f"تم {'تفعيل' if employee.is_active else 'تعطيل'} الموظف بنجاح"
            })

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "message": str(exc)
            },
            status=400
        )


@login_required
@require_POST
def employee_toggle_active_ajax_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(
        Employee.objects.select_related("user"),
        pk=pk,
    )

    try:
        with transaction.atomic():
            employee = EmployeeService.toggle_active(
                request=request,
                employee=employee,
            )

        return JsonResponse(
            {
                "success": True,
                "employee_id": employee.pk,
                "is_active": employee.is_active,
                "status_text": "نشط" if employee.is_active else "معطل",
                "message": (
                    f"تم تفعيل الموظف {employee.full_name} بنجاح"
                    if employee.is_active
                    else f"تم تعطيل الموظف {employee.full_name} بنجاح"
                ),
            }
        )

    except Exception as exc:
        return JsonResponse(
            {
                "success": False,
                "message": f"تعذر تحديث حالة الموظف: {exc}",
            },
            status=400,
        )


@login_required
@require_POST
def employee_delete_ajax_view(request, pk):
    require_staff(request.user)

    employee = get_object_or_404(
        Employee.objects.select_related("user"),
        pk=pk,
    )

    try:
        with transaction.atomic():
            employee = EmployeeService.safe_delete(
                request=request,
                employee=employee,
            )

        return JsonResponse(
            {
                "success": True,
                "employee_id": employee.pk,
                "is_active": employee.is_active,
                "status_text": "معطل",
                "message": (
                    f"تم تعطيل الموظف {employee.full_name} "
                    "بدل الحذف النهائي"
                ),
            }
        )

    except Exception as exc:
        return JsonResponse(
            {
                "success": False,
                "message": f"تعذر تنفيذ الحذف الآمن: {exc}",
            },
            status=400,
        )
    