from django.urls import path

from . import views


app_name = "breaks"


urlpatterns = [

    # ==========================================
    # قائمة الراحات
    # ==========================================
    path(
        "",
        views.breaks_list_view,
        name="list",
    ),

    # ==========================================
    # إضافة راحة
    # ==========================================
    path(
        "create/",
        views.break_create_view,
        name="create",
    ),

    # ==========================================
    # تعديل راحة
    # ==========================================
    path(
        "<int:pk>/update/",
        views.break_update_view,
        name="update",
    ),

    # ==========================================
    # تفعيل / تعطيل راحة
    # ==========================================
    path(
        "<int:pk>/toggle/",
        views.break_toggle_active_view,
        name="toggle",
    ),

    # ==========================================
    # حذف راحة
    # ==========================================
    path(
        "<int:pk>/delete/",
        views.break_delete_view,
        name="delete",
    ),
]