from __future__ import annotations

from apps.core.notification_service import NotificationService
from apps.core.services import BaseService
from apps.dashboard.models import SystemActivityLog

from .models import Employee


class EmployeeService(BaseService):
    """
    جميع العمليات الخاصة بالموظفين.
    """

    module_name = "الموظفون"

    @classmethod
    def create(cls, *, request, form):
        with cls.atomic():
            employee = form.save()

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.CREATE,
                description=f"تم إنشاء الموظف {employee.full_name}",
            )

            NotificationService.success(
                title="تم إضافة موظف جديد",
                message=f"تم إضافة الموظف {employee.full_name}",
                user=request.user,
                url="/hr/",
            )

        return employee

    @classmethod
    def update(cls, *, request, form):
        with cls.atomic():
            employee = form.save()

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم تعديل بيانات الموظف {employee.full_name}",
            )

            NotificationService.info(
                title="تم تعديل بيانات موظف",
                message=f"تم تعديل بيانات الموظف {employee.full_name}",
                user=request.user,
                url="/hr/",
            )

        return employee

    @classmethod
    def toggle_active(cls, *, request, employee):
        if employee.is_active:
            employee.work_status = Employee.WorkStatus.INACTIVE
            employee.is_active = False
            action_text = "تعطيل"
        else:
            employee.work_status = Employee.WorkStatus.ACTIVE
            employee.is_active = True
            action_text = "تفعيل"

        with cls.atomic():
            employee.save(
                update_fields=[
                    "work_status",
                    "is_active",
                    "updated_at",
                ]
            )

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم {action_text} الموظف {employee.full_name}",
            )

            NotificationService.warning(
                title=f"تم {action_text} موظف",
                message=f"تم {action_text} الموظف {employee.full_name}",
                user=request.user,
                url="/hr/",
            )

        return employee

    @classmethod
    def safe_delete(cls, *, request, employee):
        employee.work_status = Employee.WorkStatus.INACTIVE
        employee.is_active = False

        with cls.atomic():
            employee.save(
                update_fields=[
                    "work_status",
                    "is_active",
                    "updated_at",
                ]
            )

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.DELETE,
                description=f"تم تنفيذ حذف آمن للموظف {employee.full_name}",
            )

            NotificationService.danger(
                title="حذف آمن لموظف",
                message=f"تم تنفيذ حذف آمن للموظف {employee.full_name}",
                user=request.user,
                url="/hr/",
            )

        return employee