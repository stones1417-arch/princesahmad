from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import Announcement
from apps.core.file_security import validate_business_attachment


class AnnouncementForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل التعاميم الإدارية.
    """

    allowed_extensions = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
    }

    max_attachment_size = 10 * 1024 * 1024  # 10 MB

    class Meta:
        model = Announcement

        fields = [
            "title",
            "content",
            "priority",
            "attachment",
            "is_active",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "أدخل عنوان التعميم الإداري",
                    "autocomplete": "off",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "placeholder": "اكتب محتوى التعميم الإداري هنا",
                    "rows": 8,
                }
            ),
            "priority": forms.Select(),
            "attachment": forms.ClearableFileInput(
                attrs={
                    "accept": (
                        ".pdf,.doc,.docx,.xls,.xlsx,"
                        ".jpg,.jpeg,.png"
                    ),
                }
            ),
            "is_active": forms.CheckboxInput(),
        }

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()

        if len(title) < 5:
            raise ValidationError(
                "يجب ألا يقل عنوان التعميم عن 5 أحرف."
            )

        return title

    def clean_content(self):
        content = (self.cleaned_data.get("content") or "").strip()

        if len(content) < 10:
            raise ValidationError(
                "يجب ألا يقل محتوى التعميم عن 10 أحرف."
            )

        return content

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")

        if not attachment:
            return attachment

        extension = Path(attachment.name).suffix.lower()

        if extension not in self.allowed_extensions:
            raise ValidationError(
                "نوع الملف غير مسموح. الأنواع المسموحة: "
                "PDF وWord وExcel والصور."
            )

        if attachment.size > self.max_attachment_size:
            raise ValidationError(
                "حجم المرفق يجب ألا يتجاوز 10 ميجابايت."
            )

        validate_business_attachment(attachment)

        return attachment
