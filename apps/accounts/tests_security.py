from io import BytesIO
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image

from apps.accounts.forms import ProfilePhotoForm
from apps.accounts.models import AccountProfile
from apps.communications.forms import AnnouncementForm

User = get_user_model()


class SecureUploadTests(SimpleTestCase):
    def test_fake_image_is_rejected(self):
        upload = SimpleUploadedFile(
            "avatar.jpg",
            b"this is not an image",
            content_type="image/jpeg",
        )
        form = ProfilePhotoForm(files={"photo": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_valid_png_is_accepted(self):
        buffer = BytesIO()
        Image.new("RGB", (32, 32), color="green").save(buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.png",
            buffer.getvalue(),
            content_type="image/png",
        )
        form = ProfilePhotoForm(files={"photo": upload})
        self.assertTrue(form.is_valid(), form.errors)

    def test_fake_pdf_attachment_is_rejected(self):
        upload = SimpleUploadedFile(
            "notice.pdf",
            b"not a pdf",
            content_type="application/pdf",
        )
        form = AnnouncementForm(
            data={
                "title": "تعميم اختباري",
                "content": "محتوى تعميم اختباري صالح",
                "priority": "normal",
                "is_active": True,
            },
            files={"attachment": upload},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("attachment", form.errors)

    def test_invalid_extension_is_rejected(self):
        buffer = BytesIO()
        Image.new("RGB", (32, 32), color="blue").save(buffer, format="PNG")
        upload = SimpleUploadedFile(
            "avatar.exe",
            buffer.getvalue(),
            content_type="image/png",
        )
        form = ProfilePhotoForm(files={"photo": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_oversized_image_is_rejected(self):
        buffer = BytesIO()
        Image.new("RGB", (32, 32), color="red").save(buffer, format="PNG")
        payload = buffer.getvalue()
        while len(payload) < 6 * 1024 * 1024:
            payload += buffer.getvalue()

        upload = SimpleUploadedFile(
            "avatar.png",
            payload,
            content_type="image/png",
        )
        self.assertGreater(upload.size, 5 * 1024 * 1024)
        form = ProfilePhotoForm(files={"photo": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_path_traversal_name_is_rejected(self):
        class MaliciousNameUploadedFile(SimpleUploadedFile):
            @property
            def name(self):
                return self._name

            @name.setter
            def name(self, value):
                self._name = value

        buffer = BytesIO()
        Image.new("RGB", (32, 32), color="green").save(buffer, format="PNG")
        upload = MaliciousNameUploadedFile(
            "avatar.png",
            buffer.getvalue(),
            content_type="image/png",
        )
        upload.name = "../avatar.png"
        form = ProfilePhotoForm(files={"photo": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)


class ProfileImageSafetyTests(TestCase):
    def test_legacy_storage_key_returns_url_when_original_key_exists(self):
        user = User.objects.create_user(username="legacy-key-user")
        profile = AccountProfile(user=user, photo="media/profiles/2026/08/avatar.png")
        storage = Mock()
        storage.exists.side_effect = lambda name: name == "media/profiles/2026/08/avatar.png"
        storage.url.side_effect = lambda name: f"https://cdn.example/{name}"
        profile.photo.storage = storage

        self.assertEqual(
            profile.profile_image_url,
            "https://cdn.example/media/profiles/2026/08/avatar.png",
        )

    def test_modern_storage_key_returns_url_when_normalized_key_exists(self):
        user = User.objects.create_user(username="modern-key-user")
        profile = AccountProfile(user=user, photo="profiles/2026/08/avatar.png")
        storage = Mock()
        storage.exists.side_effect = lambda name: name == "profiles/2026/08/avatar.png"
        storage.url.side_effect = lambda name: f"https://cdn.example/{name}"
        profile.photo.storage = storage

        self.assertEqual(
            profile.profile_image_url,
            "https://cdn.example/profiles/2026/08/avatar.png",
        )

    def test_legacy_db_name_falls_back_to_normalized_key_when_needed(self):
        user = User.objects.create_user(username="legacy-db-user")
        profile = AccountProfile(user=user, photo="media/profiles/2026/08/avatar.png")
        storage = Mock()
        storage.exists.side_effect = lambda name: name == "profiles/2026/08/avatar.png"
        storage.url.side_effect = lambda name: f"https://cdn.example/{name}"
        profile.photo.storage = storage

        self.assertEqual(
            profile.profile_image_url,
            "https://cdn.example/profiles/2026/08/avatar.png",
        )

    def test_missing_or_unsafe_storage_keys_return_empty_string(self):
        user = User.objects.create_user(username="unsafe-key-user")

        missing_profile = AccountProfile(user=user, photo="media/profiles/2026/08/missing.png")
        missing_storage = Mock()
        missing_storage.exists.return_value = False
        missing_profile.photo.storage = missing_storage
        self.assertEqual(missing_profile.profile_image_url, "")

        unsafe_profile = AccountProfile(user=user, photo="../avatar.png")
        unsafe_storage = Mock()
        unsafe_profile.photo.storage = unsafe_storage
        self.assertEqual(unsafe_profile.profile_image_url, "")

    def test_missing_profile_photo_renders_fallback_in_topbar(self):
        user = User.objects.create_user(username="profile-fallback-user")
        AccountProfile.objects.create(user=user, photo="profiles/missing-profile.png")

        request = RequestFactory().get("/")
        request.user = user

        rendered = render_to_string("components/topbar.html", {"request": request})

        self.assertIn("topbar-account-avatar-fallback", rendered)
        self.assertNotIn("/media/profiles/missing-profile.png", rendered)

    def test_profile_page_renders_fallback_when_photo_file_is_missing(self):
        user = User.objects.create_user(
            username="profile-page-fallback",
            email="fallback@example.com",
            password="StrongPassword123!",
        )
        AccountProfile.objects.create(user=user, photo="profiles/missing-profile.png")
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("profile-user-card", response.content.decode("utf-8"))
        self.assertNotIn("/media/profiles/missing-profile.png", response.content.decode("utf-8"))
        self.assertIn("profilePhotoPreview", response.content.decode("utf-8"))

    def test_user_without_account_profile_renders_safe_fallback(self):
        user = User.objects.create_user(username="no-profile-user")
        request = RequestFactory().get("/")
        request.user = user

        rendered = render_to_string("components/topbar.html", {"request": request})

        self.assertIn("topbar-account-avatar-fallback", rendered)
        self.assertIn("no-profile-user", rendered)
