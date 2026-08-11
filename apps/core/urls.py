from django.urls import path

from . import views


app_name = "core"


urlpatterns = [
    path(
        "section/select/",
        views.set_operational_section,
        name="set-operational-section",
    ),
]