from django.urls import path

from . import views


app_name = "core"


urlpatterns = [
    path(
        "system/settings/",
        views.system_settings_view,
        name="system-settings",
    ),
    path(
        "section/select/",
        views.set_operational_section,
        name="set-operational-section",
    ),
]
