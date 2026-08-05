from django.urls import path
from . import views

app_name = "locations"

urlpatterns = [

    # ==========================================
    # لوحة إدارة المواقع والأبواب
    # ==========================================
    path(
        "",
        views.locations_dashboard_view,
        name="dashboard",
    ),

    # ==========================================
    # إضافة منطقة
    # ==========================================
    path(
        "zones/create/",
        views.zone_create_view,
        name="zone-create",
    ),

    # ==========================================
    # تعديل منطقة
    # ==========================================
    path(
        "zones/<int:pk>/update/",
        views.zone_update_view,
        name="zone-update",
    ),

    # ==========================================
    # تعديل باب
    # ==========================================
    path(
        "doors/<int:pk>/update/",
        views.door_update_view,
        name="door-update",
    ),

    # ==========================================
    # تفعيل / تعطيل باب
    # ==========================================
    path(
        "doors/<int:pk>/toggle/",
        views.door_toggle_active_view,
        name="door-toggle",
    ),
]