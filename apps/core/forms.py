from django import forms

from .models import SystemConfiguration


class SystemConfigurationForm(forms.ModelForm):
    updated_at = forms.DateTimeField(widget=forms.HiddenInput)

    class Meta:
        model = SystemConfiguration
        fields = (
            "organization_name",
            "platform_name",
            "timezone",
            "default_language",
            "support_email",
            "support_phone",
            "communications_enabled",
            "email_notifications_enabled",
            "sms_notifications_enabled",
        )
        widgets = {
            "organization_name": forms.TextInput(attrs={"dir": "rtl"}),
            "platform_name": forms.TextInput(attrs={"dir": "rtl"}),
            "timezone": forms.Select(
                choices=(("Asia/Riyadh", "Asia/Riyadh"), ("UTC", "UTC"))
            ),
        }
        labels = {
            "organization_name": "اسم الجهة",
            "platform_name": "اسم المنصة",
            "timezone": "المنطقة الزمنية",
            "default_language": "اللغة الافتراضية",
            "support_email": "البريد الإداري",
            "support_phone": "رقم التواصل",
            "communications_enabled": "الاتصالات العامة",
            "email_notifications_enabled": "إشعارات البريد",
            "sms_notifications_enabled": "إشعارات SMS",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.updated_at:
            self.fields["updated_at"].initial = self.instance.updated_at

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("email_notifications_enabled") and not cleaned.get(
            "communications_enabled"
        ):
            self.add_error(
                "email_notifications_enabled",
                "فعّل الاتصالات العامة أولًا.",
            )
        if cleaned.get("sms_notifications_enabled") and not cleaned.get(
            "communications_enabled"
        ):
            self.add_error(
                "sms_notifications_enabled",
                "فعّل الاتصالات العامة أولًا.",
            )
        return cleaned
