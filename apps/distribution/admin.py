from django.contrib import admin

from .models import DoorAssignment


@admin.register(DoorAssignment)
class DoorAssignmentAdmin(admin.ModelAdmin):
    """
    إدارة توزيعات الموظفين على الأبواب.

    سجل التوزيعات التاريخي أصبح موجودًا مركزيًا داخل:
    apps.audit.models.AssignmentHistory
    """

    list_display = (
        "employee",
        "door",
        "shift_plan",
        "role",
        "is_supervisor",
        "is_active",
        "assigned_by",
        "assigned_at",
        "updated_at",
    )

    list_filter = (
        "role",
        "is_supervisor",
        "is_active",
        "shift_plan",
        "door",
        "assigned_at",
    )

    search_fields = (
        "employee__full_name",
        "employee__employee_number",
        "door__name",
        "door__door_number",
        "shift_plan__shift_type__name",
        "notes",
    )

    readonly_fields = (
        "assigned_at",
        "updated_at",
    )

    list_select_related = (
        "employee",
        "door",
        "shift_plan",
        "shift_plan__shift_type",
        "assigned_by",
    )

    ordering = (
        "door__door_number",
        "-is_supervisor",
        "employee__employee_number",
    )

    fieldsets = (
        (
            "بيانات التوزيع",
            {
                "fields": (
                    "shift_plan",
                    "door",
                    "employee",
                    "role",
                    "is_supervisor",
                    "is_active",
                )
            },
        ),
        (
            "التفاصيل",
            {
                "fields": (
                    "notes",
                    "assigned_by",
                    "assigned_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        """
        تسجيل المستخدم الذي أنشأ التوزيع من لوحة الإدارة.
        """
        if not obj.assigned_by_id:
            obj.assigned_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )