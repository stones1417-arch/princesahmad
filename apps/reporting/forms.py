from django import forms

from apps.scheduling.models import ShiftPlan

from .models import ShiftReport


class ShiftReportForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shift_plan"].queryset = (
            ShiftPlan.objects.filter(
                is_finished=True,
                report__isnull=True,
            )
            .select_related("shift_type")
            .order_by("-date", "shift_type__name")
        )
        self.fields["shift_plan"].empty_label = "اختر وردية منتهية ومتاحة"
        self.fields["shift_plan"].label_from_instance = (
            self._shift_option_label
        )

    @staticmethod
    def _shift_option_label(shift_plan):
        label = f"{shift_plan.shift_type.name} — {shift_plan.date:%Y-%m-%d}"
        if shift_plan.start_time and shift_plan.end_time:
            label += (
                f" — {shift_plan.start_time:%H:%M}"
                f" إلى {shift_plan.end_time:%H:%M}"
            )
        return label

    class Meta:
        model = ShiftReport

        fields = [
            "report_type",
            "shift_plan",
            "summary",
            "recommendations",
        ]

        widgets = {

            "report_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "shift_plan": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "summary": forms.Textarea(
                attrs={
                    "rows": 6,
                    "class": "form-control",
                    "placeholder": "اكتب الملخص التنفيذي (للتقرير الإداري فقط)...",
                }
            ),

            "recommendations": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "form-control",
                    "placeholder": "اكتب التوصيات (للتقرير الإداري فقط)...",
                }
            ),
        }

        labels = {
            "report_type": "نوع التقرير",
            "shift_plan": "الوردية",
            "summary": "الملخص التنفيذي",
            "recommendations": "التوصيات",
        }

    def clean(self):

        cleaned = super().clean()

        report_type = cleaned.get("report_type")
        shift_plan = cleaned.get("shift_plan")
        summary = cleaned.get("summary")
        recommendations = cleaned.get("recommendations")

        if report_type == ShiftReport.ReportType.OPERATIONAL:

            if not shift_plan:
                self.add_error(
                    "shift_plan",
                    "يجب اختيار وردية للتقرير التشغيلي."
                )

            # في التقرير التشغيلي يتم إنشاء الملخص والتوصيات تلقائياً
            cleaned["summary"] = ""
            cleaned["recommendations"] = ""

        elif report_type == ShiftReport.ReportType.MANUAL:

            if not summary and not recommendations:
                raise forms.ValidationError(
                    "يجب كتابة ملخص أو توصيات للتقرير الإداري."
                )

        return cleaned
