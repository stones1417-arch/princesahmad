from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [

    path(
        "",
        views.notifications_list_view,
        name="list",
    ),

    path(
        "<int:pk>/read/",
        views.mark_notification_read_view,
        name="read",
    ),

    path(
        "read-all/",
        views.mark_all_notifications_read_view,
        name="read-all",
    ),

]