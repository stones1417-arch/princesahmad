from django.urls import path
from . import views

app_name = "ops"

urlpatterns = [
    path("", views.operations_center_view, name="operations-center"),
    path("command-center/", views.command_center_view, name="command-center"),
    path("command-center/data/", views.command_center_data_ajax, name="command-center-data"),
    path("activity-log/", views.activity_log_view, name="activity-log"),
    path("activity-log/export/excel/", views.export_activity_log_excel_view, name="activity-log-export"),
    path("doors/", views.door_status_view, name="doors"),
    path("doors/status-data/", views.door_status_data_ajax, name="door-status-data"),
    path("doors/<int:pk>/update/ajax/", views.update_door_status_ajax, name="door-update-ajax"),
    path("doors/<int:pk>/maintenance/create/ajax/", views.create_maintenance_request_ajax, name="maintenance-create-ajax"),
    path("maintenance/", views.maintenance_requests_view, name="maintenance-list"),
    path("maintenance/<int:pk>/update-status/ajax/", views.update_maintenance_status_ajax, name="maintenance-update-status-ajax"),
    path("incidents/", views.incidents_view, name="incidents"),
    path("incidents/create/", views.create_incident_ajax, name="incident-create"),
    path("incidents/<int:pk>/update/", views.update_incident_status_ajax, name="incident-update"),
]
