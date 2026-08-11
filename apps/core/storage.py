from __future__ import annotations

import logging

from cloudinary_storage.storage import MediaCloudinaryStorage


logger = logging.getLogger(__name__)


class SafeCloudinaryMediaStorage(MediaCloudinaryStorage):
    """Cloudinary storage that fails explicitly instead of falling back locally."""

    def _save(self, name, content):
        try:
            return super()._save(name, content)
        except Exception as error:
            logger.exception("Cloudinary upload failed for %s.", name)
            raise OSError("تعذر رفع الملف إلى التخزين السحابي.") from error

    def delete(self, name):
        try:
            return super().delete(name)
        except Exception as error:
            logger.exception("Cloudinary deletion failed for %s.", name)
            raise OSError("تعذر حذف الملف من التخزين السحابي.") from error

    def url(self, name):
        try:
            return super().url(name)
        except Exception as error:
            logger.exception("Cloudinary URL generation failed for %s.", name)
            raise OSError("تعذر إنشاء رابط الملف السحابي.") from error