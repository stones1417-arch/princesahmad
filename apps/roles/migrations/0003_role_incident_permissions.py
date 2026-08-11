from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("roles", "0002_role_operational_section")]

    operations = [
        migrations.AlterModelOptions(
            name="role",
            options={
                "ordering": ["name"],
                "permissions": [
                    ("view_employees", "يمكن عرض الموظفين"), ("create_employee", "يمكن إضافة موظف"),
                    ("update_employee", "يمكن تعديل موظف"), ("disable_employee", "يمكن تعطيل موظف"),
                    ("view_shifts", "يمكن عرض الورديات"), ("create_shift", "يمكن إنشاء وردية"),
                    ("activate_shift", "يمكن تفعيل وردية"), ("finish_shift", "يمكن إنهاء وردية"),
                    ("view_distribution", "يمكن عرض التوزيع"), ("assign_employees", "يمكن توزيع الموظفين"),
                    ("approve_distribution", "يمكن اعتماد التوزيع"), ("view_doors", "يمكن عرض الأبواب"),
                    ("open_door", "يمكن فتح الباب"), ("close_door", "يمكن إغلاق الباب"),
                    ("move_door_to_maintenance", "يمكن تحويل الباب إلى الصيانة"),
                    ("view_maintenance_requests", "يمكن عرض طلبات الصيانة"),
                    ("create_maintenance_request", "يمكن إنشاء بلاغ صيانة"),
                    ("approve_maintenance_request", "يمكن اعتماد طلب صيانة"),
                    ("assign_maintenance_technician", "يمكن تعيين فني صيانة"),
                    ("close_maintenance_request", "يمكن إغلاق طلب صيانة"),
                    ("create_incident", "يمكن إنشاء بلاغ تشغيلي"), ("update_incident", "يمكن تحديث بلاغ تشغيلي"),
                    ("view_reports", "يمكن عرض التقارير"), ("create_report", "يمكن إنشاء تقرير"),
                    ("update_report", "يمكن تعديل تقرير"), ("approve_report", "يمكن اعتماد تقرير"),
                    ("export_report", "يمكن تصدير تقرير"), ("view_system_logs", "يمكن عرض سجلات النظام"),
                    ("manage_users", "يمكن إدارة المستخدمين"), ("manage_backups", "يمكن إدارة النسخ الاحتياطية"),
                    ("manage_roles", "يمكن إدارة الأدوار والصلاحيات"),
                ],
                "verbose_name": "دور", "verbose_name_plural": "الأدوار والصلاحيات",
            },
        ),
    ]