from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.accounts.forms import ProfilePhotoForm
from apps.communications.forms import AnnouncementForm


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
