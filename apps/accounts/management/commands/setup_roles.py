from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.role_permissions import setup_role_permissions


class Command(BaseCommand):
    help = "إنشاء أو تحديث الأدوار المؤسسية وصلاحياتها بأمان"

    @transaction.atomic
    def handle(self, *args, **options):
        roles = setup_role_permissions()

        self.stdout.write(
            self.style.SUCCESS(
                f"تم إعداد {len(roles)} دورًا مؤسسيًا بنجاح."
            )
        )