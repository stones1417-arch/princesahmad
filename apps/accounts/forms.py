from django import forms

from apps.core.file_security import (
    validate_image_content,
)

from .models import AccountProfile


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = AccountProfile

        fields = (
            "photo",
        )

        widgets = {
            "photo": forms.ClearableFileInput(
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