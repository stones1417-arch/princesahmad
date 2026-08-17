from __future__ import annotations
from django.core.exceptions import ValidationError
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class PreviewAjaxViewTests(TestCase):
    """
    اختبارات واجهة المعاينة الديناميكية لمركز التصدير.

    تغطي:
    - اشتراط تسجيل الدخول.
    - التقرير غير الموجود.
    - الاستجابة JSON.
    - البحث.
    - الترتيب.
    - حجم الصفحة.
    - أرقام الصفحات.
    - القيم الفارغة.
    - معالجة أخطاء خدمة المعاينة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="preview_ajax_user",
            password="StrongPassword123!",
            is_staff=True,
        )

    def setUp(self):
        self.client.force_login(
            self.user
        )

        self.report_key = "employees"

        self.url = reverse(
            "exports_center:preview-data",
            kwargs={
                "report_key": self.report_key,
            },
        )

    def _build_export_column(
        self,
        *,
        key: str,
        header: str,
        values_by_pk: dict[int, object],
        data_type: str = "text",
    ):
        """
        إنشاء ExportColumn وهمي متوافق مع الواجهة.
        """

        column = MagicMock()

        column.key = key
        column.header = header
        column.source = key
        column.data_type = data_type

        column.get_value.side_effect = (
            lambda record: values_by_pk.get(
                record.pk
            )
        )

        return column

    def _build_report(
        self,
        *,
        columns,
    ):
        """
        إنشاء تعريف تقرير وهمي.
        """

        report = MagicMock()

        report.key = self.report_key
        report.title = "تقرير الموظفين"
        report.module = "hr"

        report.get_columns.return_value = (
            columns
        )

        report.supports_format.return_value = (
            True
        )

        return report

    def _build_records(self):
        """
        إنشاء سجلات وهمية للمعاينة.
        """

        records = []

        employee_data = [
            (
                1,
                "أحمد محمد",
                "1001",
                True,
            ),
            (
                2,
                "خالد علي",
                "1002",
                False,
            ),
            (
                3,
                "محمد صالح",
                "1003",
                True,
            ),
        ]

        for (
            pk,
            full_name,
            employee_number,
            is_active,
        ) in employee_data:
            record = MagicMock()

            record.pk = pk
            record.full_name = full_name
            record.employee_number = (
                employee_number
            )
            record.is_active = is_active

            record.get_absolute_url.return_value = (
                f"/hr/{pk}/"
            )

            records.append(
                record
            )

        return records

    def _mock_report_and_preview(
        self,
    ):
        """
        تجهيز التقرير والسجلات الوهمية.
        """

        records = self._build_records()

        name_column = self._build_export_column(
            key="full_name",
            header="اسم الموظف",
            values_by_pk={
                record.pk: record.full_name
                for record in records
            },
        )

        number_column = (
            self._build_export_column(
                key="employee_number",
                header="الرقم الوظيفي",
                values_by_pk={
                    record.pk: (
                        record.employee_number
                    )
                    for record in records
                },
                data_type="number",
            )
        )

        active_column = (
            self._build_export_column(
                key="is_active",
                header="الحالة",
                values_by_pk={
                    record.pk: record.is_active
                    for record in records
                },
                data_type="boolean",
            )
        )

        report = self._build_report(
            columns=[
                name_column,
                number_column,
                active_column,
            ]
        )

        preview_data = {
            "records": records,
            "records_count": 3,
            "preview_count": 3,
            "indicators": {},
        }

        return (
            report,
            preview_data,
        )

    def test_login_is_required(self):
        """
        المستخدم غير المسجل يتم تحويله إلى تسجيل الدخول.
        """

        self.client.logout()

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertIn(
            "login",
            response.url,
        )

    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_unknown_report_returns_404(
        self,
        mocked_get_report_definition,
    ):
        """
        التقرير غير الموجود يعيد 404.
        """

        mocked_get_report_definition.side_effect = (
            KeyError("Unknown report")
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_gender_filter_is_normalized_to_section_for_preview(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        عند تمرير operational_section يجب إضافة section بنفس القيمة قبل المعاينة.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "operational_section": "female",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            mocked_preview_report.called
        )

        called_kwargs = mocked_preview_report.call_args.kwargs

        self.assertEqual(
            called_kwargs["filters"].get("operational_section"),
            "female",
        )

        self.assertEqual(
            called_kwargs["filters"].get("section"),
            "female",
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_returns_valid_json_payload(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        يجب أن يعيد المسار بنية JSON المؤسسية.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "page": 1,
                "page_size": 25,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response["Content-Type"],
            "application/json",
        )

        payload = response.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertEqual(
            payload["report"]["key"],
            self.report_key,
        )

        self.assertEqual(
            payload["report"]["title"],
            "تقرير الموظفين",
        )

        self.assertEqual(
            len(
                payload["columns"]
            ),
            3,
        )

        self.assertEqual(
            len(
                payload["rows"]
            ),
            3,
        )

        self.assertEqual(
            payload["pagination"]["page"],
            1,
        )

        self.assertEqual(
            payload["pagination"]["page_size"],
            25,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_columns_do_not_expose_export_column_objects(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        لا يتم إرسال كائن ExportColumn داخل JSON.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url
        )

        payload = response.json()

        first_column = payload[
            "columns"
        ][0]

        self.assertNotIn(
            "export_column",
            first_column,
        )

        self.assertEqual(
            first_column["key"],
            "full_name",
        )

        self.assertEqual(
            first_column["header"],
            "اسم الموظف",
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_preview_uses_selected_columns_in_requested_order(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        report, preview_data = self._mock_report_and_preview()
        mocked_get_report_definition.return_value = report
        mocked_preview_report.return_value = preview_data

        response = self.client.get(
            self.url,
            [
                ("selected_columns", "employee_number"),
                ("selected_columns", "full_name"),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [column["key"] for column in response.json()["columns"]],
            ["employee_number", "full_name"],
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_search_filters_preview_rows(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        البحث يعرض الصفوف المطابقة فقط.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "search": "خالد",
                "page_size": 25,
            },
        )

        payload = response.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertEqual(
            len(
                payload["rows"]
            ),
            1,
        )

        self.assertEqual(
            payload["rows"][0]["values"][0][
                "value"
            ],
            "خالد علي",
        )

        self.assertEqual(
            payload["summary"][
                "filtered_preview_records"
            ],
            1,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_sorting_ascending(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        يمكن ترتيب الأعمدة تصاعديًا.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "sort": "employee_number",
                "direction": "asc",
                "page_size": 25,
            },
        )

        payload = response.json()

        employee_numbers = [
            row["values"][1]["value"]
            for row in payload["rows"]
        ]

        self.assertEqual(
            employee_numbers,
            [
                "1001",
                "1002",
                "1003",
            ],
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_sorting_descending(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        يمكن ترتيب الأعمدة تنازليًا.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "sort": "employee_number",
                "direction": "desc",
                "page_size": 25,
            },
        )

        payload = response.json()

        employee_numbers = [
            row["values"][1]["value"]
            for row in payload["rows"]
        ]

        self.assertEqual(
            employee_numbers,
            [
                "1003",
                "1002",
                "1001",
            ],
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_invalid_sort_key_is_ignored(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        لا يسمح بالترتيب باستخدام مفتاح غير معرف.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "sort": "password",
                "direction": "desc",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertTrue(
            payload["ok"]
        )

        self.assertEqual(
            len(
                payload["rows"]
            ),
            3,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_invalid_page_size_uses_default(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        حجم الصفحة غير المسموح يعود إلى القيمة الافتراضية.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "page_size": 9999,
            },
        )

        payload = response.json()

        self.assertEqual(
            payload["pagination"]["page_size"],
            50,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_page_is_never_less_than_one(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        رقم الصفحة السالب أو الصفر يتحول إلى الصفحة الأولى.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url,
            {
                "page": -10,
                "page_size": 25,
            },
        )

        payload = response.json()

        self.assertEqual(
            payload["pagination"]["page"],
            1,
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_boolean_values_are_preserved(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        القيم المنطقية تصل إلى الواجهة كـ Boolean.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url
        )

        payload = response.json()

        first_boolean_item = (
            payload["rows"][0]["values"][2]
        )

        self.assertIs(
            first_boolean_item["value"],
            True,
        )

        self.assertEqual(
            first_boolean_item["type"],
            "boolean",
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_record_url_is_included_when_available(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        يظهر رابط السجل عند وجود get_absolute_url.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url
        )

        payload = response.json()

        self.assertEqual(
            payload["rows"][0]["record_url"],
            "/hr/1/",
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_response_disables_browser_cache(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        بيانات المعاينة الحساسة لا يتم تخزينها في كاش المتصفح.
        """

        (
            report,
            preview_data,
        ) = self._mock_report_and_preview()

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.return_value = (
            preview_data
        )

        response = self.client.get(
            self.url
        )

        self.assertIn(
            "no-store",
            response["Cache-Control"],
        )

        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_service_error_returns_400_json(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        أخطاء الخدمة المعروفة تعيد JSON واضحًا.
        """

        report = MagicMock()

        report.key = self.report_key
        report.title = "تقرير الموظفين"

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.side_effect = (
            ValidationError(
                "قيمة الفلتر غير صحيحة."
            )
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        payload = response.json()

        self.assertFalse(
            payload["ok"]
        )

        self.assertIn(
            "قيمة الفلتر غير صحيحة",
            payload["message"],
        )

    @patch(
        "apps.exports_center.views."
        "preview_report"
    )
    @patch(
        "apps.exports_center.views."
        "get_report_definition"
    )
    def test_unexpected_error_returns_safe_message(
        self,
        mocked_get_report_definition,
        mocked_preview_report,
    ):
        """
        الخطأ غير المتوقع لا يكشف تفاصيل داخلية للمستخدم.
        """

        report = MagicMock()

        report.key = self.report_key
        report.title = "تقرير الموظفين"

        mocked_get_report_definition.return_value = (
            report
        )

        mocked_preview_report.side_effect = (
            RuntimeError(
                "Database password or internal detail"
            )
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            500,
        )

        payload = response.json()

        self.assertFalse(
            payload["ok"]
        )

        self.assertNotIn(
            "Database password",
            payload["message"],
        )

        self.assertEqual(
            payload["message"],
            (
                "حدث خطأ غير متوقع أثناء "
                "تحميل بيانات المعاينة."
            ),
        )