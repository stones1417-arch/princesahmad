from django.urls import path

from . import views


app_name = "communications"


urlpatterns = [
    path("dashboard/", views.communications_dashboard_view, name="dashboard"),
    path("logs/", views.communication_logs_view, name="logs"),
    path("logs/<int:pk>/", views.communication_log_detail_view, name="log-detail"),
    path("assignment-messages/", views.assignment_messages_view, name="assignment-messages"),
    path("assignment-messages/<int:pk>/", views.assignment_message_detail_view, name="assignment-message-detail"),
    path("assignment-messages/<int:pk>/retry/", views.assignment_message_retry_view, name="assignment-message-retry"),
    path("provider/", views.authentica_provider_view, name="provider"),
    path("webhooks/authentica/", views.authentica_webhook_view, name="authentica-webhook"),
    path(
        "",
        views.announcement_list_view,
        name="list",
    ),

    path(
        "create/",
        views.announcement_create_view,
        name="create",
    ),

    path(
        "<int:pk>/",
        views.announcement_detail_view,
        name="detail",
    ),

    path(
        "<int:pk>/edit/",
        views.announcement_update_view,
        name="edit",
    ),

    path(
        "<int:pk>/toggle-status/",
        views.announcement_toggle_status_view,
        name="toggle-status",
    ),

    path(
        "<int:pk>/delete/",
        views.announcement_delete_view,
        name="delete",
    ),
]