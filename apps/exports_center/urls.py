from django.urls import path

from . import views


app_name = "exports_center"


urlpatterns = [
    path(
        "",
        views.dashboard_view,
        name="dashboard",
    ),

    path(
        "report/<str:report_key>/filters/",
        views.filters_view,
        name="filters",
    ),

    path(
        "report/<str:report_key>/preview/",
        views.preview_view,
        name="preview",
    ),

    path(
        (
            "report/<str:report_key>/"
            "export/<str:export_format>/"
        ),
        views.export_view,
        name="export",
    ),
path(
    "logs/",
    views.logs_view,
    name="logs",
),
    path(
        "export/submit/",
        views.export_submit_view,
        name="export-submit",
    ),
    path(
        "logs/<int:export_log_id>/download/",
        views.download_export_view,
        name="download-export",
    ),
]
