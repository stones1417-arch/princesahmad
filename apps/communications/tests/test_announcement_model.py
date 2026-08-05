from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.communications.models import Announcement


User = get_user_model()


TEST_MEDIA_ROOT = tempfile.mkdtemp(
    prefix="communications-tests-"
)


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT
)
class AnnouncementModelTests(TestCase):
    """
    اختبارات نموذج التعاميم الإدارية.
    """

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

        shutil.rmtree(
            TEST_MEDIA_ROOT,
            ignore_errors=True,
        )

    def setUp(self):
        self.user = User.objects.create_user(
            username="announcement_model_user",
            email="announcement-model@example.com",
            password="StrongPassword123!",
            is_active=True,
            is_staff=True,
        )

    def create_announcement(
        self,
        **overrides,
    ) -> Announcement:
        data = {
            "title": "تعميم إداري اختباري",
            "content": "هذا محتوى التعميم الإداري.",
            "priority": Announcement.Priority.NORMAL,
            "is_active": True,
            "created_by": self.user,
        }

        data.update(
            overrides
        )

        return Announcement.objects.create(
            **data
        )

    def test_announcement_can_be_created(self):
        """
        يجب إنشاء تعميم إداري صحيح.
        """

        announcement = self.create_announcement()

        self.assertIsNotNone(
            announcement.pk
        )

        self.assertTrue(
            announcement.is_active
        )

        self.assertEqual(
            announcement.created_by_id,
            self.user.pk,
        )

    def test_default_priority_is_normal(self):
        """
        الأولوية الافتراضية يجب أن تكون عادية.
        """

        announcement = Announcement.objects.create(
            title="تعميم بأولوية افتراضية",
            content="اختبار الأولوية الافتراضية.",
            created_by=self.user,
        )

        self.assertEqual(
            announcement.priority,
            Announcement.Priority.NORMAL,
        )

    def test_priority_choices_are_complete(self):
        """
        يجب دعم الأولويات الثلاث.
        """

        values = {
            value
            for value, _label
            in Announcement.Priority.choices
        }

        self.assertEqual(
            values,
            {
                Announcement.Priority.NORMAL,
                Announcement.Priority.IMPORTANT,
                Announcement.Priority.URGENT,
            },
        )

    def test_string_representation_returns_title(self):
        """
        النص الظاهر للتعميم يجب أن يكون عنوانه.
        """

        announcement = self.create_announcement()

        self.assertEqual(
            str(announcement),
            announcement.title,
        )

    def test_attachment_type_pdf(self):
        """
        يجب التعرف على ملف PDF.
        """

        announcement = self.create_announcement(
            attachment=SimpleUploadedFile(
                "announcement.pdf",
                b"%PDF-1.4 test",
                content_type="application/pdf",
            )
        )

        self.assertEqual(
            announcement.attachment_type,
            "pdf",
        )

    def test_attachment_type_image(self):
        """
        يجب التعرف على ملفات الصور.
        """

        announcement = self.create_announcement(
            attachment=SimpleUploadedFile(
                "announcement.png",
                b"fake-image-content",
                content_type="image/png",
            )
        )

        self.assertEqual(
            announcement.attachment_type,
            "image",
        )

    def test_attachment_type_word(self):
        """
        يجب التعرف على ملفات Word.
        """

        announcement = self.create_announcement(
            attachment=SimpleUploadedFile(
                "announcement.docx",
                b"fake-word-content",
                content_type=(
                    "application/vnd.openxmlformats-"
                    "officedocument.wordprocessingml.document"
                ),
            )
        )

        self.assertEqual(
            announcement.attachment_type,
            "word",
        )

    def test_attachment_type_excel(self):
        """
        يجب التعرف على ملفات Excel.
        """

        announcement = self.create_announcement(
            attachment=SimpleUploadedFile(
                "announcement.xlsx",
                b"fake-excel-content",
                content_type=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
            )
        )

        self.assertEqual(
            announcement.attachment_type,
            "excel",
        )

    def test_unknown_attachment_type_returns_file(self):
        """
        الامتداد غير المعروف يعرض كملف عام.
        """

        announcement = self.create_announcement(
            attachment=SimpleUploadedFile(
                "announcement.zip",
                b"fake-zip-content",
                content_type="application/zip",
            )
        )

        self.assertEqual(
            announcement.attachment_type,
            "file",
        )

    def test_without_attachment_returns_none(self):
        """
        غياب المرفق يجب أن يعيد None.
        """

        announcement = self.create_announcement(
            attachment=None,
        )

        self.assertIsNone(
            announcement.attachment_type
        )

    def test_announcements_are_ordered_newest_first(self):
        """
        الترتيب الافتراضي يجب أن يكون من الأحدث للأقدم.
        """

        first = self.create_announcement(
            title="التعميم الأول",
        )

        second = self.create_announcement(
            title="التعميم الثاني",
        )

        ids = list(
            Announcement.objects.values_list(
                "id",
                flat=True,
            )
        )

        self.assertEqual(
            ids,
            [
                second.pk,
                first.pk,
            ],
        )

    def test_deleting_creator_keeps_announcement(self):
        """
        حذف منشئ التعميم لا يحذف التعميم.
        """

        announcement = self.create_announcement()
        announcement_pk = announcement.pk

        self.user.delete()

        announcement.refresh_from_db()

        self.assertEqual(
            announcement.pk,
            announcement_pk,
        )

        self.assertIsNone(
            announcement.created_by_id
        )