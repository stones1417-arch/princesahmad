from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import models, transaction


class Role(models.Model):
    """
    دور مؤسسي داخل المنصة.
    """

    class OperationalSection(models.TextChoices):
        ALL = (
            "all",
            "الكل",
        )

        MALE = (
            "male",
            "رجالي",
        )

        FEMALE = (
            "female",
            "نسائي",
        )

    code = models.SlugField(
        max_length=80,
        unique=True,
        db_index=True,
        verbose_name="رمز الدور",
    )

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="اسم الدور",
    )

    description = models.TextField(
        blank=True,
        verbose_name="وصف الدور",
    )

    operational_section = models.CharField(
        max_length=10,
        choices=OperationalSection.choices,
        default=OperationalSection.ALL,
        db_index=True,
        verbose_name="نطاق القسم التشغيلي",
        help_text=(
            "يحدد القسم الذي يستطيع صاحب الدور "
            "الوصول إلى بياناته."
        ),
    )

    group = models.OneToOneField(
        Group,
        on_delete=models.PROTECT,
        related_name="platform_role",
        verbose_name="مجموعة الصلاحيات",
    )

    is_system_role = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="دور نظامي",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشط",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "دور"
        verbose_name_plural = "الأدوار والصلاحيات"

        permissions = [
            ("view_employees", "يمكن عرض الموظفين"),
            ("create_employee", "يمكن إضافة موظف"),
            ("update_employee", "يمكن تعديل موظف"),
            ("disable_employee", "يمكن تعطيل موظف"),

            ("view_shifts", "يمكن عرض الورديات"),
            ("create_shift", "يمكن إنشاء وردية"),
            ("activate_shift", "يمكن تفعيل وردية"),
            ("finish_shift", "يمكن إنهاء وردية"),

            ("view_distribution", "يمكن عرض التوزيع"),
            ("assign_employees", "يمكن توزيع الموظفين"),
            ("approve_distribution", "يمكن اعتماد التوزيع"),

            ("view_doors", "يمكن عرض الأبواب"),
            ("open_door", "يمكن فتح الباب"),
            ("close_door", "يمكن إغلاق الباب"),
            (
                "move_door_to_maintenance",
                "يمكن تحويل الباب إلى الصيانة",
            ),

            (
                "view_maintenance_requests",
                "يمكن عرض طلبات الصيانة",
            ),
            (
                "create_maintenance_request",
                "يمكن إنشاء بلاغ صيانة",
            ),
            (
                "approve_maintenance_request",
                "يمكن اعتماد طلب صيانة",
            ),
            (
                "assign_maintenance_technician",
                "يمكن تعيين فني صيانة",
            ),
            (
                "close_maintenance_request",
                "يمكن إغلاق طلب صيانة",
            ),

            ("view_reports", "يمكن عرض التقارير"),
            ("create_report", "يمكن إنشاء تقرير"),
            ("update_report", "يمكن تعديل تقرير"),
            ("approve_report", "يمكن اعتماد تقرير"),
            ("export_report", "يمكن تصدير تقرير"),

            ("view_system_logs", "يمكن عرض سجلات النظام"),
            ("manage_users", "يمكن إدارة المستخدمين"),
            ("manage_backups", "يمكن إدارة النسخ الاحتياطية"),
            ("manage_roles", "يمكن إدارة الأدوار والصلاحيات"),
        ]

    def clean(self):
        super().clean()

        if self.code:
            self.code = self.code.strip().lower()

        if self.name:
            self.name = self.name.strip()

        errors = {}

        if not self.code:
            errors["code"] = "رمز الدور مطلوب."

        if not self.name:
            errors["name"] = "اسم الدور مطلوب."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.group_id and self.group.name != self.name:
            self.group.name = self.name
            self.group.save(
                update_fields=["name"]
            )

        return super().save(*args, **kwargs)

    @property
    def permissions(self):
        return self.group.permissions.all()

    def set_permissions(
        self,
        permissions: list[Permission],
    ) -> None:
        self.group.permissions.set(permissions)

    def __str__(self):
        return self.name

    def can_access_section(
        self,
        section: str,
    ) -> bool:
        normalized_section = str(
            section
            or ""
        ).strip().lower()

        return (
            self.operational_section
            == self.OperationalSection.ALL
            or self.operational_section
            == normalized_section
        )


class UserRole(models.Model):
    """
    إسناد دور مؤسسي إلى مستخدم.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_role_assignments",
        verbose_name="المستخدم",
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="user_assignments",
        verbose_name="الدور",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="نشط",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_platform_roles",
        verbose_name="أُسند بواسطة",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإسناد",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    class Meta:
        ordering = [
            "user",
            "role",
        ]

        verbose_name = "دور مستخدم"
        verbose_name_plural = "أدوار المستخدمين"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "role",
                ],
                name="unique_platform_user_role",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "is_active",
                ],
                name="user_role_active_idx",
            ),
            models.Index(
                fields=[
                    "role",
                    "is_active",
                ],
                name="role_user_active_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.is_active and not self.role.is_active:
            raise ValidationError(
                {
                    "role": "لا يمكن إسناد دور غير نشط.",
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()

        previous_role_id = None
        previous_active = False

        if self.pk:
            previous = (
                UserRole.objects
                .filter(pk=self.pk)
                .values(
                    "role_id",
                    "is_active",
                )
                .first()
            )

            if previous:
                previous_role_id = previous["role_id"]
                previous_active = previous["is_active"]

        with transaction.atomic():
            result = super().save(*args, **kwargs)

            if (
                previous_role_id
                and previous_role_id != self.role_id
                and previous_active
            ):
                previous_role = (
                    Role.objects
                    .filter(pk=previous_role_id)
                    .select_related("group")
                    .first()
                )

                if previous_role:
                    self.user.groups.remove(
                        previous_role.group
                    )

            if self.is_active:
                self.user.groups.add(
                    self.role.group
                )
            else:
                self.user.groups.remove(
                    self.role.group
                )

            return result

    def delete(self, *args, **kwargs):
        user = self.user
        group = self.role.group

        with transaction.atomic():
            result = super().delete(
                *args,
                **kwargs,
            )

            other_active_assignments = (
                UserRole.objects
                .filter(
                    user=user,
                    role__group=group,
                    is_active=True,
                )
                .exists()
            )

            if not other_active_assignments:
                user.groups.remove(group)

        return result

    def __str__(self):
        return f"{self.user} - {self.role}"