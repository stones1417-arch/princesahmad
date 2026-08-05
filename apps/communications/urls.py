from django.urls import path

from . import views


app_name = "communications"


urlpatterns = [
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