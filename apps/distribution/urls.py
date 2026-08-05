from django.urls import path

from . import views

app_name = "distribution"

urlpatterns = [
    path("", views.distribution_dashboard_view, name="dashboard"),
    path("history/", views.assignment_history_view, name="history"),
    path("create/", views.assignment_create_view, name="create"),
    path("<int:pk>/deactivate/", views.assignment_deactivate_view, name="deactivate"),
    path("validate/", views.assignment_validate_view, name="validate"),
    path("auto-assign/", views.assignment_auto_assign_view, name="auto-assign"),
    path("rebalance/preview/", views.assignment_rebalance_preview_view, name="rebalance-preview"),
    path("rebalance/", views.assignment_rebalance_view, name="rebalance"),
    path("send-sms/", views.assignment_send_sms_view, name="send-sms"),
]
