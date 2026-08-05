from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.views.decorators.http import require_GET

from apps.roles.decorators import permission_required
from apps.roles.services.permission_registry import (
    PlatformPermissions,
)

from .services.shift_excel_exporter import (
    export_shift_excel_response,
)
from .services.shift_pdf_exporter import (
    export_shift_pdf_response,
)


ALLOWED_SECTIONS = frozenset(
    {
        "all",
        "distribution",
        "maintenance",
        "incidents",
    }
)

ALLOWED_FORMATS = frozenset(
    {
        "excel",
        "pdf",
    }
)


@login_required
@permission_required(
    PlatformPermissions.EXPORT_REPORT,
    message="ليس لديك صلاحية تصدير تقارير الورديات.",
)
@require_GET
def export_shift_bundle(
    request: HttpRequest,
) -> HttpResponse:
    """
    استقبال طلب تصدير الوردية والتحقق من مدخلاته فقط.

    لا ينشئ هذا الـ View ملفات Excel أو PDF مباشرة،
    وإنما يمرر الطلب إلى طبقة الخدمات المسؤولة عن التصدير.

    الصلاحية المطلوبة:
    roles.export_report
    """

    shift_plan_value = (
        request.GET.get(
            "shift_plan",
            "",
        )
        or ""
    ).strip()

    section = (
        request.GET.get(
            "section",
            "all",
        )
        or "all"
    ).strip().lower()

    export_format = (
        request.GET.get(
            "format",
            "excel",
        )
        or "excel"
    ).strip().lower()

    if not shift_plan_value.isdigit():
        return HttpResponseBadRequest(
            "يجب اختيار وردية صحيحة."
        )

    shift_plan_id = int(
        shift_plan_value
    )

    if shift_plan_id <= 0:
        return HttpResponseBadRequest(
            "معرّف الوردية غير صحيح."
        )

    if section not in ALLOWED_SECTIONS:
        return HttpResponseBadRequest(
            "قسم التصدير المطلوب غير صحيح."
        )

    if export_format not in ALLOWED_FORMATS:
        return HttpResponseBadRequest(
            "صيغة التصدير غير مدعومة."
        )

    if export_format == "pdf":
        return export_shift_pdf_response(
            request=request,
            shift_plan_id=shift_plan_id,
            section=section,
        )

    return export_shift_excel_response(
        request=request,
        shift_plan_id=shift_plan_id,
        section=section,
    )