from django.urls import path
from . import views

app_name = "scheduling"

urlpatterns = [

    path(
        "workforce/",
        views.workforce_center_view,
        name="workforce-center",
    ),

    path(
        "",
        views.current_shift_view,
        name="current",
    ),

    path(
        "status/",
        views.shifts_status_view,
        name="status",
    ),

    path(
        "shifts/<int:pk>/activate/ajax/",
        views.activate_shift_ajax,
        name="activate-shift-ajax",
    ),

    path(
        "shifts/upsert/ajax/",
        views.upsert_shift_plan_ajax,
        name="shift-upsert-ajax",
    ),

    path(
        "assignments/",
        views.shift_assignment_list_view,
        name="assignments",
    ),

    path(
        "assignments/create/",
        views.shift_assignment_create_view,
        name="assignment-create",
    ),

    path(
        "assignments/<int:pk>/confirm/",
        views.shift_assignment_confirm_view,
        name="assignment-confirm",
    ),

    path(
        "assignments/<int:pk>/delete/",
        views.shift_assignment_delete_view,
        name="assignment-delete",
    ),
    path(
    "shifts/seasonal/create/ajax/",
    views.create_seasonal_schedule_ajax,
    name="seasonal-shift-create-ajax",
),
]
