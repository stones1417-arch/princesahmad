from pathlib import Path

from django import forms

from apps.hr.models import Employee
from apps.roles.models import Role


class RegistrationApprovalForm(forms.Form):
    operational_section = forms.ChoiceField(label="القسم التشغيلي", choices=Employee.OperationalSection.choices)
    role_code = forms.ModelChoiceField(label="الدور الوظيفي", queryset=Role.objects.none(), to_field_name="code")

    def __init__(self, *args, roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role_code"].queryset = roles if roles is not None else Role.objects.none()


class RegistrationRejectionForm(forms.Form):
    reason = forms.CharField(label="سبب الرفض", widget=forms.Textarea, min_length=3, max_length=1000)

from apps.core.file_security import safe_uploaded_basename, validate_image_content

from .models import AccountProfile


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = AccountProfile

        fields = (
            "photo",
        )

        widgets = {
            "photo": forms.FileInput(
                attrs={
                    "accept": (
                        "image/jpeg,"
                        "image/png,"
                        "image/webp"
                    ),
                    "class": (
                        "profile-photo-input"
                    ),
                    "aria-label": (
                        "اختيار صورة شخصية"
                    ),
                }
            )
        }

    def clean_photo(self):
        photo = self.cleaned_data.get(
            "photo"
        )

        if not photo:
            return photo

        name = getattr(photo, "name", "") or ""
        try:
            name = safe_uploaded_basename(name)
        except forms.ValidationError:
            raise
        except Exception as error:
            raise forms.ValidationError("اسم الملف غير آمن.") from error

        extension = Path(name).suffix.lower()
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}

        if extension not in allowed_extensions:
            raise forms.ValidationError(
                "الصيغ المسموحة: JPG أو JPEG أو PNG أو WEBP."
            )

        if photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("حجم الصورة يجب ألا يتجاوز 5 ميجابايت.")

        content_type = getattr(
            photo,
            "content_type",
            "",
        )

        allowed = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if (
            content_type
            and content_type not in allowed
        ):
            raise forms.ValidationError(
                (
                    "الصيغ المسموحة: "
                    "JPG أو PNG أو WEBP."
                )
            )

        validate_image_content(
            photo
        )

        return photo


class ProfileContactForm(forms.ModelForm):
    """
    تعديل بيانات الاتصال الخاصة بالحساب.

    رقم الجوال يجب أن يكون بصيغة E.164
    حتى يكون صالحًا مباشرة لـAuthentica.
    """

    class Meta:
        model = AccountProfile

        fields = (
            "phone_number",
        )

        widgets = {
            "phone_number": forms.TextInput(
                attrs={
                    "class": (
                        "profile-contact-input"
                    ),
                    "placeholder": (
                        "+9665XXXXXXXX"
                    ),
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "dir": "ltr",
                    "maxlength": "16",
                }
            )
        }

    def clean_phone_number(self):
        value = (
            self.cleaned_data.get(
                "phone_number"
            )
            or ""
        ).strip()

        return value
