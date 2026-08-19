from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.exports_center.models import ExportLog


class Command(BaseCommand):
    help = "Print non-secret storage backend diagnostics without uploading files."

    def handle(self, *args, **options):
        export_storage = ExportLog._meta.get_field("file").storage
        configured = bool(settings.STORAGES.get("default", {}).get("BACKEND"))
        self.stdout.write(f"STORAGE_CLASS={default_storage.__class__.__module__}.{default_storage.__class__.__name__}")
        self.stdout.write(f"EXPORT_FILE_STORAGE_CLASS={export_storage.__class__.__module__}.{export_storage.__class__.__name__}")
        self.stdout.write(f"MEDIA_CONFIGURED={configured}")
