from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from apps.core.storage import SafeCloudinaryMediaStorage


class CloudinaryStorageTests(SimpleTestCase):
    def setUp(self):
        self.storage = object.__new__(SafeCloudinaryMediaStorage)

    def test_development_uses_local_media_storage(self):
        self.assertEqual(
            settings.STORAGES["default"]["BACKEND"],
            "django.core.files.storage.FileSystemStorage",
        )

    @patch(
        "apps.core.storage.MediaCloudinaryStorage._save",
        return_value="profiles/avatar.jpg",
    )
    def test_upload_returns_cloudinary_name(self, mocked_save):
        result = self.storage._save(
            "profiles/avatar.jpg",
            ContentFile(b"image data"),
        )

        self.assertEqual(result, "profiles/avatar.jpg")
        mocked_save.assert_called_once()

    @patch(
        "apps.core.storage.MediaCloudinaryStorage.delete"
    )
    def test_delete_delegates_to_cloudinary(self, mocked_delete):
        self.storage.delete("profiles/avatar.jpg")

        mocked_delete.assert_called_once_with("profiles/avatar.jpg")

    @patch(
        "apps.core.storage.MediaCloudinaryStorage.url",
        return_value="https://res.cloudinary.com/demo/image/upload/avatar.jpg",
    )
    def test_url_returns_cloudinary_url(self, mocked_url):
        result = self.storage.url("profiles/avatar.jpg")

        self.assertEqual(
            result,
            "https://res.cloudinary.com/demo/image/upload/avatar.jpg",
        )
        mocked_url.assert_called_once_with("profiles/avatar.jpg")

    @patch(
        "apps.core.storage.MediaCloudinaryStorage._save",
        side_effect=RuntimeError("Cloudinary unavailable"),
    )
    def test_upload_failure_raises_safe_error(self, mocked_save):
        with self.assertRaisesRegex(
            OSError,
            "تعذر رفع الملف",
        ):
            self.storage._save(
                "profiles/avatar.jpg",
                ContentFile(b"image data"),
            )

        mocked_save.assert_called_once()

    @patch(
        "apps.core.storage.MediaCloudinaryStorage.delete",
        side_effect=RuntimeError("Cloudinary unavailable"),
    )
    def test_delete_failure_raises_safe_error(self, mocked_delete):
        with self.assertRaisesRegex(
            OSError,
            "تعذر حذف الملف",
        ):
            self.storage.delete("profiles/avatar.jpg")

        mocked_delete.assert_called_once_with("profiles/avatar.jpg")

    @patch(
        "apps.core.storage.MediaCloudinaryStorage.url",
        side_effect=RuntimeError("Cloudinary unavailable"),
    )
    def test_url_failure_raises_safe_error(self, mocked_url):
        with self.assertRaisesRegex(
            OSError,
            "تعذر إنشاء رابط الملف",
        ):
            self.storage.url("profiles/avatar.jpg")

        mocked_url.assert_called_once_with("profiles/avatar.jpg")
