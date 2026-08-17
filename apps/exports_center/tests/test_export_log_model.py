from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.exports_center.models import ExportLog
from apps.exports_center.services.shift_excel_exporter import export_shift_excel_response
from apps.exports_center.services.shift_pdf_exporter import export_shift_pdf_response


User = get_user_model()


class ExportServiceImportTests(SimpleTestCase):
    def test_shift_export_services_import_cleanly(self):
        self.assertTrue(callable(export_shift_excel_response))
        self.assertTrue(callable(export_shift_pdf_response))


class ExportLogModelTests(TestCase):
    """
    اختبارات نموذج سجل عمليات التصدير.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="export_log_user",
            email="export-log@example.com",
            password="StrongPassword123!",
            is_active=True,
        )

    def create_log(
        self,
        **overrides,
    ) -> ExportLog:
        data = {
            "user": self.user,
            "module": "الموظفون",
            "report_key": "employees",
            "report_name": "سجل الموظفين",
            "export_format": ExportLog.ExportFormat.EXCEL,
            "status": ExportLog.ExportStatus.PROCESSING,
            "filters": {},
            "metadata": {},
        }

        data.update(overrides)

        return ExportLog.objects.create(
            **data
        )

    def test_export_log_can_be_created(self):
        """
        يجب إنشاء سجل تصدير بنجاح.
        """

        export_log = self.create_log()

        self.assertIsNotNone(
            export_log.pk
        )

        self.assertEqual(
            export_log.status,
            ExportLog.ExportStatus.PROCESSING,
        )

    def test_report_name_falls_back_to_module(self):
        """
        عند غياب اسم التقرير يستخدم اسم القسم.
        """

        export_log = self.create_log(
            report_name="",
            module="الورديات",
        )

        self.assertEqual(
            export_log.report_name,
            "الورديات",
        )

    def test_string_representation_contains_report_and_status(self):
        """
        النص الظاهر للسجل يحتوي اسم التقرير وحالته.
        """

        export_log = self.create_log()

        text = str(export_log)

        self.assertIn(
            "سجل الموظفين",
            text,
        )

        self.assertIn(
            "Excel",
            text,
        )

        self.assertIn(
            "قيد المعالجة",
            text,
        )

    def test_extension_is_returned_in_lowercase(self):
        """
        يجب استخراج امتداد الملف بأحرف صغيرة.
        """

        export_log = self.create_log(
            file_name="EMPLOYEES.XLSX",
        )

        self.assertEqual(
            export_log.extension,
            ".xlsx",
        )

    def test_empty_extension_returns_empty_string(self):
        """
        عند غياب الملف لا يوجد امتداد.
        """

        export_log = self.create_log(
            file_name="",
            storage_path="",
        )

        self.assertEqual(
            export_log.extension,
            "",
        )

    def test_file_size_is_formatted_as_bytes(self):
        """
        الحجم الصغير يعرض بالبايت.
        """

        export_log = self.create_log(
            file_size=500,
        )

        self.assertEqual(
            export_log.formatted_file_size,
            "500 بايت",
        )

    def test_file_size_is_formatted_as_kilobytes(self):
        """
        يجب عرض الحجم بالكيلوبايت.
        """

        export_log = self.create_log(
            file_size=2048,
        )

        self.assertEqual(
            export_log.formatted_file_size,
            "2.0 كيلوبايت",
        )

    def test_file_size_is_formatted_as_megabytes(self):
        """
        يجب عرض الحجم بالميجابايت.
        """

        export_log = self.create_log(
            file_size=2 * 1024 * 1024,
        )

        self.assertEqual(
            export_log.formatted_file_size,
            "2.0 ميجابايت",
        )

    def test_file_size_is_formatted_as_gigabytes(self):
        """
        يجب عرض الحجم بالجيجابايت.
        """

        export_log = self.create_log(
            file_size=2 * 1024 * 1024 * 1024,
        )

        self.assertEqual(
            export_log.formatted_file_size,
            "2.0 جيجابايت",
        )

    def test_success_without_file_is_not_ready_for_download(self):
        """
        النجاح دون ملف محفوظ لا يسمح بالتنزيل.
        """

        export_log = self.create_log(
            status=ExportLog.ExportStatus.SUCCESS,
        )

        self.assertFalse(
            export_log.is_ready_for_download
        )

    def test_success_with_file_is_ready_for_download(self):
        """
        النجاح مع وجود الملف يسمح بالتنزيل.
        """

        export_log = self.create_log()

        export_log.file.save(
            "employees.xlsx",
            ContentFile(b"excel-content"),
            save=True,
        )

        export_log.status = (
            ExportLog.ExportStatus.SUCCESS
        )
        export_log.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        self.assertTrue(
            export_log.is_ready_for_download
        )

    def test_mark_processing_sets_start_time(self):
        """
        التحويل إلى المعالجة يسجل وقت البداية.
        """

        export_log = self.create_log(
            status=ExportLog.ExportStatus.PENDING,
        )

        export_log.mark_processing()

        export_log.refresh_from_db()

        self.assertEqual(
            export_log.status,
            ExportLog.ExportStatus.PROCESSING,
        )

        self.assertIsNotNone(
            export_log.started_at
        )

        self.assertIsNone(
            export_log.completed_at
        )

        self.assertEqual(
            export_log.error_message,
            "",
        )

    def test_mark_success_updates_export_data(self):
        """
        نجاح العملية يحدث عدد السجلات وبيانات الملف.
        """

        export_log = self.create_log()

        export_log.mark_success(
            records_count=25,
            file_size=4096,
            file_name="employees.xlsx",
            storage_path="exports/employees.xlsx",
            metadata={
                "sheet": "الموظفون",
            },
        )

        export_log.refresh_from_db()

        self.assertEqual(
            export_log.status,
            ExportLog.ExportStatus.SUCCESS,
        )

        self.assertEqual(
            export_log.records_count,
            25,
        )

        self.assertEqual(
            export_log.file_size,
            4096,
        )

        self.assertEqual(
            export_log.file_name,
            "employees.xlsx",
        )

        self.assertEqual(
            export_log.storage_path,
            "exports/employees.xlsx",
        )

        self.assertEqual(
            export_log.metadata,
            {
                "sheet": "الموظفون",
            },
        )

        self.assertIsNotNone(
            export_log.completed_at
        )

        self.assertEqual(
            export_log.error_message,
            "",
        )

    def test_mark_success_does_not_allow_negative_counts(self):
        """
        عدد السجلات وحجم الملف لا يصبحان سالبين.
        """

        export_log = self.create_log()

        export_log.mark_success(
            records_count=-5,
            file_size=-100,
        )

        export_log.refresh_from_db()

        self.assertEqual(
            export_log.records_count,
            0,
        )

        self.assertEqual(
            export_log.file_size,
            0,
        )

    def test_mark_failed_saves_error_message(self):
        """
        فشل العملية يحفظ رسالة الخطأ.
        """

        export_log = self.create_log()

        export_log.mark_failed(
            "تعذر إنشاء ملف التصدير.",
            metadata={
                "stage": "excel",
            },
        )

        export_log.refresh_from_db()

        self.assertEqual(
            export_log.status,
            ExportLog.ExportStatus.FAILED,
        )

        self.assertEqual(
            export_log.error_message,
            "تعذر إنشاء ملف التصدير.",
        )

        self.assertEqual(
            export_log.metadata,
            {
                "stage": "excel",
            },
        )

        self.assertIsNotNone(
            export_log.completed_at
        )

    def test_failed_error_message_is_limited(self):
        """
        يجب ألا تتجاوز رسالة الخطأ الحد المسموح.
        """

        export_log = self.create_log()

        export_log.mark_failed(
            "x" * 6000
        )

        export_log.refresh_from_db()

        self.assertEqual(
            len(export_log.error_message),
            5000,
        )

    def test_duration_seconds_is_calculated(self):
        """
        يجب حساب مدة المعالجة بالثواني.
        """

        export_log = self.create_log()

        now = timezone.now()

        export_log.started_at = now
        export_log.completed_at = (
            now + timedelta(seconds=12.5)
        )

        self.assertEqual(
            export_log.duration_seconds,
            12.5,
        )

    def test_duration_is_none_without_completion(self):
        """
        لا توجد مدة قبل انتهاء العملية.
        """

        export_log = self.create_log()

        export_log.started_at = timezone.now()
        export_log.completed_at = None

        self.assertIsNone(
            export_log.duration_seconds
        )

        self.assertEqual(
            export_log.formatted_duration,
            "—",
        )

    def test_duration_is_formatted_as_seconds(self):
        """
        يجب عرض المدة القصيرة بالثواني.
        """

        export_log = self.create_log()

        now = timezone.now()

        export_log.started_at = now
        export_log.completed_at = (
            now + timedelta(seconds=15)
        )

        self.assertEqual(
            export_log.formatted_duration,
            "15.00 ثانية",
        )

    def test_duration_is_formatted_as_minutes(self):
        """
        يجب عرض المدة بالدقائق والثواني.
        """

        export_log = self.create_log()

        now = timezone.now()

        export_log.started_at = now
        export_log.completed_at = (
            now + timedelta(
                minutes=2,
                seconds=5,
            )
        )

        self.assertEqual(
            export_log.formatted_duration,
            "2 دقيقة و5 ثانية",
        )

    def test_register_download_increments_counter(self):
        """
        تسجيل التنزيل يزيد العداد.
        """

        export_log = self.create_log(
            download_count=0,
        )

        export_log.register_download()

        self.assertEqual(
            export_log.download_count,
            1,
        )

        self.assertIsNotNone(
            export_log.last_downloaded_at
        )

    def test_register_download_can_be_called_more_than_once(self):
        """
        يجب زيادة العداد في كل عملية تنزيل.
        """

        export_log = self.create_log(
            download_count=2,
        )

        export_log.register_download()
        export_log.register_download()

        self.assertEqual(
            export_log.download_count,
            4,
        )

    def test_file_save_updates_name_path_and_size(self):
        """
        حفظ الملف يحدّث الاسم والمسار والحجم.
        """

        export_log = self.create_log()

        content = b"sample-export-content"

        export_log.file.save(
            "sample.csv",
            ContentFile(content),
            save=True,
        )

        export_log.refresh_from_db()

        self.assertEqual(
            export_log.file_name,
            "sample.csv",
        )

        self.assertTrue(
            export_log.storage_path.endswith(
                "sample.csv"
            )
        )

        self.assertEqual(
            export_log.file_size,
            len(content),
        )

    def tearDown(self):
        """
        حذف الملفات التي أنشأتها الاختبارات.
        """

        for export_log in ExportLog.objects.all():
            if export_log.file:
                export_log.file.delete(
                    save=False
                )