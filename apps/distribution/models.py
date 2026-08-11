from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.hr.models import Employee
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan


class DoorAssignment(models.Model):
    """
    توزيع موظف على باب معين داخل وردية.

    يدعم التشغيل:
    - الرجالي.
    - النسائي.
    - الأبواب المشتركة بين القسمين.

    قواعد التوزيع:
    - الباب الرجالي يقبل التسكين الرجالي فقط.
    - الباب النسائي يقبل التسكين النسائي فقط.
    - الباب المشترك يقبل تسكينًا رجاليًا أو نسائيًا.
    - يسمح للباب المشترك بمشرف رجالي ومشرفة نسائية.
    - يمنع وجود مشرفين نشطين من القسم نفسه على الباب نفسه.
    - يمنع تسكين الموظف نفسه أكثر من مرة في الوردية.

    سجل عمليات الإنشاء والتعديل والنقل والإلغاء
    يُحفظ مركزيًا داخل:
    apps.audit.models.AssignmentHistory
    """

    class Role(models.TextChoices):
        SUPERVISOR = (
            "supervisor",
            "مشرف باب",
        )
        MONITOR = (
            "monitor",
            "مراقب باب",
        )
        SUPPORT = (
            "support",
            "مساند",
        )
        TECHNICIAN = (
            "technician",
            "فني صيانة",
        )

    class AssignmentSection(models.TextChoices):
        MALE = (
            "male",
            "رجالي",
        )
        FEMALE = (
            "female",
            "نسائي",
        )

    # ==================================================
    # العلاقات الأساسية
    # ==================================================

    shift_plan = models.ForeignKey(
        ShiftPlan,
        on_delete=models.CASCADE,
        related_name="door_assignments",
        verbose_name="الوردية",
        db_index=True,
    )

    door = models.ForeignKey(
        Door,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="الباب",
        db_index=True,
    )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="door_assignments",
        verbose_name="الموظف",
        db_index=True,
    )

    # ==================================================
    # قسم التسكين
    # ==================================================

    section = models.CharField(
        max_length=10,
        choices=AssignmentSection.choices,
        default=AssignmentSection.MALE,
        db_index=True,
        verbose_name="قسم التسكين",
        help_text=(
            "حدد هل التسكين تابع للقسم الرجالي "
            "أو القسم النسائي."
        ),
    )

    # ==================================================
    # الدور والحالة
    # ==================================================

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MONITOR,
        verbose_name="الدور على الباب",
        db_index=True,
    )

    is_supervisor = models.BooleanField(
        default=False,
        verbose_name="مشرف الباب",
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="توزيع نشط",
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    # ==================================================
    # بيانات التدقيق
    # ==================================================

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_door_assignments",
        verbose_name="تم التوزيع بواسطة",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ التوزيع",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        verbose_name = "توزيع باب"
        verbose_name_plural = "توزيعات الأبواب"

        ordering = [
            "door__door_number",
            "section",
            "-is_supervisor",
            "employee__employee_number",
        ]

        constraints = [
            # منع تكرار الموظف على الباب نفسه
            # داخل الوردية والقسم نفسه.
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "door",
                    "employee",
                    "section",
                ],
                name=(
                    "unique_employee_door_"
                    "shift_section"
                ),
            ),

            # الموظف لا يمكن تسكينه أكثر من مرة
            # داخل الوردية، حتى لو اختلف الباب أو القسم.
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "employee",
                ],
                condition=models.Q(
                    is_active=True,
                ),
                name=(
                    "unique_active_employee_"
                    "assignment_per_shift"
                ),
            ),

            # مشرف واحد نشط لكل:
            # وردية + باب + قسم.
            models.UniqueConstraint(
                fields=[
                    "shift_plan",
                    "door",
                    "section",
                ],
                condition=models.Q(
                    is_supervisor=True,
                    is_active=True,
                ),
                name=(
                    "unique_active_supervisor_"
                    "door_shift_section"
                ),
            ),

            # ضمان أن القسم رجالي أو نسائي فقط.
            models.CheckConstraint(
                condition=models.Q(
                    section__in=[
                        "male",
                        "female",
                    ],
                ),
                name=(
                    "assignment_valid_section"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "shift_plan",
                ],
                name="dist_assign_shift_idx",
            ),
            models.Index(
                fields=[
                    "door",
                ],
                name="dist_assign_door_idx",
            ),
            models.Index(
                fields=[
                    "employee",
                ],
                name="dist_assign_employee_idx",
            ),
            models.Index(
                fields=[
                    "section",
                ],
                name="dist_assign_section_idx",
            ),
            models.Index(
                fields=[
                    "role",
                ],
                name="dist_assign_role_idx",
            ),
            models.Index(
                fields=[
                    "is_active",
                ],
                name="dist_assign_active_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "door",
                    "section",
                    "is_active",
                ],
                name="dist_shift_door_sec_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "employee",
                    "is_active",
                ],
                name="dist_shift_emp_active_idx",
            ),
            models.Index(
                fields=[
                    "shift_plan",
                    "section",
                    "is_active",
                ],
                name="dist_shift_sec_active_idx",
            ),
        ]

        permissions = [
            (
                "can_assign_door_employee",
                "يمكن توزيع موظف على باب",
            ),
            (
                "can_assign_door_supervisor",
                "يمكن تعيين مشرف باب",
            ),
            (
                "can_assign_male_section",
                "يمكن التوزيع على القسم الرجالي",
            ),
            (
                "can_assign_female_section",
                "يمكن التوزيع على القسم النسائي",
            ),
            (
                "can_view_distribution_dashboard",
                "يمكن عرض لوحة توزيع الأبواب",
            ),
            (
                "can_auto_assign_employees",
                "يمكن تنفيذ التوزيع التلقائي",
            ),
            (
                "can_rebalance_distribution",
                "يمكن إعادة توازن التوزيع",
            ),
        ]

    # ==================================================
    # العرض النصي
    # ==================================================

    def __str__(self) -> str:
        return (
            f"{self.employee.full_name} – "
            f"{self.door} – "
            f"{self.get_section_display()} "
            f"({self.get_role_display()})"
        )

    # ==================================================
    # أدوات داخلية
    # ==================================================

    def _synchronize_section_with_door(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        مزامنة قسم التسكين مع تصنيف الباب.

        الباب الرجالي:
            يتم اعتماد القسم الرجالي تلقائيًا.

        الباب النسائي:
            يتم اعتماد القسم النسائي تلقائيًا.

        الباب المشترك:
            يبقى القسم حسب اختيار المستخدم.
        """

        if not self.door_id:
            return

        door_section = (
            self.door.operational_section
        )

        if (
            door_section
            == Door.OperationalSection.MALE
        ):
            self.section = (
                self.AssignmentSection.MALE
            )

        elif (
            door_section
            == Door.OperationalSection.FEMALE
        ):
            self.section = (
                self.AssignmentSection.FEMALE
            )

        elif (
            door_section
            == Door.OperationalSection.SHARED
        ):
            if self.section not in {
                self.AssignmentSection.MALE,
                self.AssignmentSection.FEMALE,
            }:
                errors["section"] = (
                    "يجب تحديد قسم التسكين للباب "
                    "المشترك: رجالي أو نسائي."
                )

        else:
            errors["door"] = (
                "تصنيف القسم التشغيلي للباب غير صالح."
            )

    def _validate_door_supports_section(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التأكد من أن الباب يسمح بالقسم المختار.
        """

        if not self.door_id:
            return

        if (
            self.section
            == self.AssignmentSection.MALE
            and not self.door.supports_male_operations
        ):
            errors["section"] = (
                "هذا الباب مخصص للقسم النسائي، "
                "ولا يقبل تسكينًا رجاليًا."
            )

        if (
            self.section
            == self.AssignmentSection.FEMALE
            and not self.door.supports_female_operations
        ):
            errors["section"] = (
                "هذا الباب مخصص للقسم الرجالي، "
                "ولا يقبل تسكينًا نسائيًا."
            )

    def _validate_employee_section(
        self,
        errors: dict[str, str],
    ) -> None:
        """
        التحقق من توافق الموظف مع قسم التسكين.

        يعتمد على القسم التشغيلي الصريح للموظف.
        """

        if not self.employee_id:
            return

        employee_section = str(
            getattr(
                self.employee,
                "operational_section",
                "",
            )
            or ""
        ).strip().lower()

        if not employee_section:
            return

        male_values = {
            "male",
            "m",
            "ذكر",
            "رجالي",
        }

        female_values = {
            "female",
            "f",
            "أنثى",
            "انثى",
            "نسائي",
        }

        if (
            employee_section in male_values
            and self.section
            != self.AssignmentSection.MALE
        ):
            errors["employee"] = (
                "لا يمكن تسكين موظف رجالي "
                "ضمن القسم النسائي."
            )

        if (
            employee_section in female_values
            and self.section
            != self.AssignmentSection.FEMALE
        ):
            errors["employee"] = (
                "لا يمكن تسكين موظفة ضمن "
                "القسم الرجالي."
            )

    # ==================================================
    # التحقق
    # ==================================================

    def clean(self) -> None:
        """
        التحقق من جميع قواعد التوزيع.
        """

        super().clean()

        errors: dict[str, str] = {}

        # ----------------------------------------------
        # مزامنة حالة المشرف والدور
        # ----------------------------------------------

        if (
            self.role
            == self.Role.SUPERVISOR
        ):
            self.is_supervisor = True

        elif self.is_supervisor:
            self.role = (
                self.Role.SUPERVISOR
            )

        else:
            self.is_supervisor = False

        # ----------------------------------------------
        # التحقق من الوردية
        # ----------------------------------------------

        if self.shift_plan_id:
            if not self.shift_plan.is_active:
                errors["shift_plan"] = (
                    "لا يمكن التوزيع على وردية "
                    "غير نشطة."
                )

            if getattr(
                self.shift_plan,
                "is_finished",
                False,
            ):
                errors["shift_plan"] = (
                    "لا يمكن التوزيع على وردية "
                    "منتهية."
                )

        # ----------------------------------------------
        # التحقق من الباب والقسم
        # ----------------------------------------------

        if self.door_id:
            if not self.door.is_active:
                errors["door"] = (
                    "لا يمكن التوزيع على باب "
                    "غير نشط."
                )

            self._synchronize_section_with_door(
                errors
            )

            self._validate_door_supports_section(
                errors
            )

        # ----------------------------------------------
        # التحقق من الموظف
        # ----------------------------------------------

        if self.employee_id:
            if not self.employee.is_active:
                errors["employee"] = (
                    "لا يمكن تسكين موظف غير نشط."
                )

            elif (
                self.employee.work_status
                != Employee.WorkStatus.ACTIVE
            ):
                errors["employee"] = (
                    "لا يمكن تسكين موظف ليس "
                    "على رأس العمل."
                )

            elif not self.employee.can_work_on_doors:
                errors["employee"] = (
                    "الموظف غير مصرح له بالعمل "
                    "على الأبواب."
                )

            self._validate_employee_section(
                errors
            )

        # ----------------------------------------------
        # التحقق من الفني
        # ----------------------------------------------

        if (
            self.employee_id
            and self.role
            == self.Role.TECHNICIAN
            and not self.employee.can_execute_maintenance
        ):
            errors["role"] = (
                "الموظف ليس ضمن فريق الصيانة."
            )

        # ----------------------------------------------
        # منع تكرار الموظف داخل الوردية
        # ----------------------------------------------

        if (
            self.shift_plan_id
            and self.employee_id
            and self.is_active
        ):
            employee_assignment_query = (
                DoorAssignment.objects.filter(
                    shift_plan_id=(
                        self.shift_plan_id
                    ),
                    employee_id=(
                        self.employee_id
                    ),
                    is_active=True,
                )
            )

            if self.pk:
                employee_assignment_query = (
                    employee_assignment_query.exclude(
                        pk=self.pk,
                    )
                )

            if employee_assignment_query.exists():
                errors["employee"] = (
                    "الموظف مسكن مسبقًا في هذه "
                    "الوردية."
                )

        # ----------------------------------------------
        # منع تكرار مشرف القسم على الباب
        # ----------------------------------------------

        if (
            self.shift_plan_id
            and self.door_id
            and self.section
            and self.is_supervisor
            and self.is_active
        ):
            supervisor_query = (
                DoorAssignment.objects.filter(
                    shift_plan_id=(
                        self.shift_plan_id
                    ),
                    door_id=self.door_id,
                    section=self.section,
                    is_supervisor=True,
                    is_active=True,
                )
            )

            if self.pk:
                supervisor_query = (
                    supervisor_query.exclude(
                        pk=self.pk,
                    )
                )

            if supervisor_query.exists():
                errors["is_supervisor"] = (
                    "يوجد مشرف نشط مسجل مسبقًا "
                    "لهذا الباب ضمن القسم نفسه."
                )

        if errors:
            raise ValidationError(
                errors
            )

    # ==================================================
    # الحفظ
    # ==================================================

    def save(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        حفظ التوزيع بعد تنفيذ التحقق الكامل.
        """

        self.full_clean()

        update_fields = kwargs.get(
            "update_fields"
        )

        if update_fields is not None:
            normalized_update_fields = set(
                update_fields
            )

            normalized_update_fields.update(
                {
                    "section",
                    "role",
                    "is_supervisor",
                }
            )

            kwargs["update_fields"] = list(
                normalized_update_fields
            )

        super().save(
            *args,
            **kwargs,
        )

    # ==================================================
    # خصائص الأدوار
    # ==================================================

    @property
    def is_technician(self) -> bool:
        return (
            self.role
            == self.Role.TECHNICIAN
        )

    @property
    def is_monitor(self) -> bool:
        return (
            self.role
            == self.Role.MONITOR
        )

    @property
    def is_support(self) -> bool:
        return (
            self.role
            == self.Role.SUPPORT
        )

    @property
    def role_display(self) -> str:
        return self.get_role_display()

    # ==================================================
    # خصائص القسم
    # ==================================================

    @property
    def is_male_section(self) -> bool:
        """
        هل التسكين تابع للقسم الرجالي؟
        """

        return (
            self.section
            == self.AssignmentSection.MALE
        )

    @property
    def is_female_section(self) -> bool:
        """
        هل التسكين تابع للقسم النسائي؟
        """

        return (
            self.section
            == self.AssignmentSection.FEMALE
        )

    @property
    def section_display(self) -> str:
        """
        الاسم العربي لقسم التسكين.
        """

        return self.get_section_display()