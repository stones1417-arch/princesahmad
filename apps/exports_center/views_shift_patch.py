from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest

from apps.roles.decorators import permission_required
from apps.roles.services.permission_registry import (
    PlatformPermissions,
)

from .shift_export_service import (
    export_shift_excel_response,
    export_shift_pdf_response,
)


@login_required
@permission_required(
    PlatformPermissions.EXPORT_REPORT,
    message="ليس لديك صلاحية تصدير بيانات الورديات.",
)
def export_shift_bundle(request):
    shift_plan_id = request.GET.get(
        "shift_plan",
        "",
    ).strip()

    section = request.GET.get(
        "section",
        "all",
    ).strip()

    export_format = request.GET.get(
        "format",
        "excel",
    ).strip()

    allowed_sections = {
        "all",
        "distribution",
        "maintenance",
        "incidents",
    }

    if not shift_plan_id.isdigit():
        return HttpResponseBadRequest(
            "يجب اختيار وردية محددة."
        )

    if section not in allowed_sections:
        return HttpResponseBadRequest(
            "نوع البيانات غير صحيح."
        )

    if export_format == "pdf":
        return export_shift_pdf_response(
            request,
            int(shift_plan_id),
            section,
        )

    return export_shift_excel_response(
        request,
        int(shift_plan_id),
        section,
    )