from .export_logger import (
    complete_export_log,
    create_processing_log,
    fail_export_log,
)
from .shift_data_service import (
    get_shift_export_data,
    get_shift_records_count,
)
def export_shift_excel_response(
    request,
    shift_plan_id: int,
    section: str,
) -> HttpResponse:
    data = get_shift_export_data(
        shift_plan_id,
    )

    shift_plan = data["shift_plan"]

    file_name = (
        f"shift_"
        f"{shift_plan.shift_type.name}_"
        f"{shift_plan.date}_"
        f"{section}.xlsx"
    ).replace(" ", "_")

    export_log = create_processing_log(
        request=request,
        module=(
            f"تقرير وردية "
            f"{shift_plan.shift_type.name}"
        ),
        report_key="shift_bundle",
        file_name=file_name,
        export_format=ExportLog.ExportFormat.EXCEL,
        filters={
            "shift_plan": shift_plan.pk,
            "section": section,
        },
    )

    try:
        content = build_shift_excel(
            data=data,
            section=section,
        )

        records_count = get_shift_records_count(
            data=data,
            section=section,
        )

        complete_export_log(
            export_log=export_log,
            content=content,
            records_count=records_count,
        )

        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{file_name}"; '
            f"filename*=UTF-8''{quote(file_name)}"
        )

        response["Content-Length"] = str(
            len(content)
        )

        return response

    except Exception as exc:
        fail_export_log(
            export_log=export_log,
            exception=exc,
        )
        raise