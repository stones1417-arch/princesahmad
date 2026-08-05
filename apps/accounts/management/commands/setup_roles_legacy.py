from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


ROLES = {
    "door_supervisor": [
        "can_update_door_status",
        "can_create_maintenance",
    ],

    "maintenance_tech": [
        "can_update_maintenance",
    ],

    "assistant_shift_leader": [
        "can_update_door_status",
        "can_edit_shift_status",
    ],

    "shift_leader": [
        "can_activate_shift",
        "can_edit_shift_status",
        "can_update_door_status",
    ],

    "general_supervisor": [
        "can_activate_shift",
        "can_edit_shift_status",
        "can_update_door_status",
        "can_create_maintenance",
        "can_update_maintenance",
    ],
}


class Command(BaseCommand):
    help = "إنشاء الأدوار والصلاحيات"

    def handle(self, *args, **kwargs):
        for group_name, perms in ROLES.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            for codename in perms:
                try:
                    perm = Permission.objects.get(codename=codename)
                    group.permissions.add(perm)
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️ الصلاحية غير موجودة: {codename}")
                    )

        self.stdout.write(self.style.SUCCESS("✅ تم إعداد الأدوار بنجاح"))
