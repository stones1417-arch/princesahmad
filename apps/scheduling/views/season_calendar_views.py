from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from apps.scheduling.models import ShiftPlan


@login_required
def seasonal_calendar_events(request):
    shifts = (
        ShiftPlan.objects
        .filter(season__isnull=False)
        .select_related(
            "season",
            "seasonal_template",
        )
        .order_by("date", "start_time")
    )

    events = []

    for shift in shifts:
        events.append(
            {
                "id": shift.pk,
                "title": (
                    f"{shift.season.name} - "
                    f"{shift.seasonal_template.name}"
                ),
                "start": (
                    f"{shift.date}T{shift.start_time}"
                ),
                "end": (
                    f"{shift.date}T{shift.end_time}"
                ),
                "extendedProps": {
                    "season": shift.season.name,
                    "active": shift.is_active,
                    "finished": shift.is_finished,
                },
            }
        )

    return JsonResponse(
        events,
        safe=False,
    )