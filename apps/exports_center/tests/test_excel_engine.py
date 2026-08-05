from __future__ import annotations

from datetime import datetime

from django.test import SimpleTestCase
from django.utils import timezone

from apps.exports_center.services.excel_engine import ExcelExportEngine


class ExcelValueSafetyTests(SimpleTestCase):
    def test_aware_datetime_is_converted_to_excel_safe_datetime(self):
        value = timezone.make_aware(datetime(2026, 8, 2, 12, 30))

        result = ExcelExportEngine._safe_excel_value(value)

        self.assertIsNone(result.tzinfo)

    def test_formula_like_text_is_not_executable(self):
        result = ExcelExportEngine._safe_excel_value("=HYPERLINK(\"bad\")")

        self.assertTrue(result.startswith("'="))
