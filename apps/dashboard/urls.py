from django.urls import path

from . import views
from .activity_views import (
    system_activity_logs_view,
)
from .system_logs_export_views import (
    export_system_logs_excel,
)
from .system_views import system_center_view


app_name = "dashboard"


urlpatterns = [
    path(
        "system/",
        system_center_view,
        name="system-center",
    ),
    # ==========================================
    # لوحة التحكم الرئيسية
    # ==========================================
    path(
        "",
        views.dashboard_view,
        name="index",
    ),

    # ==========================================
    # سجل نشاط النظام
    # ==========================================
    path(
        "system-logs/",
        system_activity_logs_view,
        name="system-logs",
    ),

    # ==========================================
    # تصدير سجل نشاط النظام إلى Excel
    # ==========================================
    path(
        "system-logs/export/excel/",
        export_system_logs_excel,
        name="system-logs-export-excel",
    ),
]
