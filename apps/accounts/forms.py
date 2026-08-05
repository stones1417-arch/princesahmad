from django import forms

from .models import AccountProfile
from apps.core.file_security import validate_image_content


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = AccountProfile
        fields = ("photo",)
        widgets = {
            "photo": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp",
                    "class": "profile-photo-input",
                    "aria-label": "اختيار صورة شخصية",
                }
            )
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not photo:
            return photo

        content_type = getattr(photo, "content_type", "")
        allowed = {"image/jpeg", "image/png", "image/webp"}
        if content_type and content_type not in allowed:
            raise forms.ValidationError("الصيغ المسموحة: JPG أو PNG أو WEBP.")
        validate_image_content(photo)
        return photo
