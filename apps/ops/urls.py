from django.urls import path
from . import views

app_name = "ops"

urlpatterns = [
    path("leadership/department/", views.supervisory_command_center_view, {"center": "department"}, name="department-command-center"),
    path("leadership/administrative/", views.supervisory_command_center_view, {"center": "administrative"}, name="administrative-command-center"),
    path("leadership/executive/", views.supervisory_command_center_view, {"center": "executive"}, name="executive-command-center"),
    path("leadership/incidents/<int:pk>/", views.supervisory_command_center_view, {"center": "detail"}, name="supervisory-incident-detail"),
    path("leadership/incidents/<int:pk>/actions/", views.create_supervisory_action_view, name="supervisory-action-create"),
    path("leadership/actions/<int:pk>/respond/", views.respond_to_update_request_view, name="supervisory-request-respond"),
    path("leadership/actions/<int:pk>/resolve/", views.resolve_update_request_view, name="supervisory-request-resolve"),
    path("leadership/actions/<int:pk>/acknowledge/", views.acknowledge_directive_view, name="supervisory-directive-acknowledge"),
    path("leadership/actions/<int:pk>/complete/", views.complete_directive_view, name="supervisory-directive-complete"),
    path("leadership/delegations/", views.create_leadership_delegation_view, name="leadership-delegation-create"),
    path("leadership/delegations/<int:pk>/revoke/", views.revoke_leadership_delegation_view, name="leadership-delegation-revoke"),
    path("", views.operations_center_view, name="operations-center"),
    path("command-center/", views.command_center_view, name="command-center"),
    path("command-center/data/", views.command_center_data_ajax, name="command-center-data"),
    path("activity-log/", views.activity_log_view, name="activity-log"),
    path("activity-log/export/excel/", views.export_activity_log_excel_view, name="activity-log-export"),
    path("doors/", views.door_status_view, name="doors"),
    path("doors/status-data/", views.door_status_data_ajax, name="door-status-data"),
    path("doors/coverage-settings/", views.door_coverage_settings_view, name="door-coverage-settings"),
    path("doors/staff-targets/", views.update_door_staff_targets, name="door-staff-targets"),
    path("doors/<int:pk>/incident-status/", views.door_incident_followup_ajax, name="door-incident-followup"),
    path("doors/<int:pk>/update/ajax/", views.update_door_status_ajax, name="door-update-ajax"),
    path("doors/<int:pk>/maintenance/create/ajax/", views.create_maintenance_request_ajax, name="maintenance-create-ajax"),
    path("maintenance/", views.maintenance_requests_view, name="maintenance-list"),
    path("maintenance/<int:pk>/update-status/ajax/", views.update_maintenance_status_ajax, name="maintenance-update-status-ajax"),
    path("incidents/", views.incidents_view, name="incidents"),
    path("incidents/create/", views.create_incident_ajax, name="incident-create"),
    path(
        "doors/<int:engineering_door_pk>/incidents/create/",
        views.create_incident_ajax,
        name="engineering-incident-create",
    ),
    path("incidents/<int:pk>/update/", views.update_incident_status_ajax, name="incident-update"),
    path("incidents/<int:pk>/escalate/", views.escalate_incident_ajax, name="incident-escalate"),
    path("incidents/<int:pk>/convert-maintenance/", views.convert_incident_to_maintenance_ajax, name="incident-convert-maintenance"),
    path("incidents/<int:pk>/shift-update/", views.add_incident_shift_update_ajax, name="incident-shift-update"),
]
