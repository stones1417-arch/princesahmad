from django.core.management.base import BaseCommand, CommandError

from apps.roles.services.role_manager import setup_default_roles


class Command(BaseCommand):
    help = "إنشاء الأدوار المؤسسية الافتراضية وتحديث صلاحياتها."

    def handle(self, *args, **options):
        self.stdout.write(
            "جارٍ إعداد الأدوار والصلاحيات المؤسسية..."
        )

        try:
            roles = setup_default_roles()

        except Exception as error:
            raise CommandError(
                f"فشل إعداد الأدوار: {error}"
            ) from error

        for role in roles:
            permission_count = (
                role.group.permissions.count()
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"تم تجهيز الدور: "
                    f"{role.name} "
                    f"({permission_count} صلاحية)"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "تم إعداد جميع الأدوار المؤسسية بنجاح."
            )
        )