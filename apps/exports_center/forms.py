from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError


class FilterForm(forms.Form):
	"""Generic filter form used by the exports center filters page.

	The form is intentionally permissive and uses GET so it can be embedded
	in links for preview/export.
	"""

	q = forms.CharField(
		required=False,
		label="بحث",
		widget=forms.TextInput(attrs={"placeholder": "ابحث باسم الموظف أو الرقم أو أي بيانات أخرى..."}),
	)

	date_from = forms.DateField(required=False, label="من تاريخ")
	date_to = forms.DateField(required=False, label="إلى تاريخ")

	preview_limit = forms.IntegerField(
		required=False,
		min_value=1,
		max_value=200,
		initial=50,
		label="حد المعاينة",
	)

	def clean(self):
		cleaned = super().clean()

		date_from = cleaned.get("date_from")
		date_to = cleaned.get("date_to")

		if date_from and date_to and date_from > date_to:
			raise ValidationError("حقل 'من تاريخ' لا يمكن أن يكون بعد 'إلى تاريخ'.")

		return cleaned


class InstitutionalContactForm(forms.Form):
	"""Simple contact form for institutional page."""

	name = forms.CharField(max_length=120, label="الاسم", required=True)
	email = forms.EmailField(label="البريد الإلكتروني", required=True)
	message = forms.CharField(
		label="الرسالة",
		widget=forms.Textarea(attrs={"rows": 6}),
		required=True,
	)

	def clean_message(self):
		text = self.cleaned_data.get("message", "").strip()
		if len(text) < 10:
			raise forms.ValidationError("الرسالة قصيرة جداً؛ اكتب تفاصيل أكثر.")
		return text
