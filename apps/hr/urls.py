from django.urls import path

from . import views


app_name = "hr"


urlpatterns = [

    # ==========================================
    # قائمة الموظفين
    # ==========================================
    path(
        "",
        views.employee_list_view,
        name="list",
    ),

    # ==========================================
    # إضافة موظف
    # ==========================================
    path(
        "create/",
        views.employee_create_view,
        name="create",
    ),

    # ==========================================
    # تعديل موظف
    # ==========================================
    path(
        "<int:pk>/update/",
        views.employee_update_view,
        name="update",
    ),

    # ==========================================
    # تفعيل / تعطيل موظف بالطريقة التقليدية
    # ==========================================
    path(
        "<int:pk>/toggle-active/",
        views.employee_toggle_active_view,
        name="toggle-active",
    ),

    # ==========================================
    # حذف آمن بالطريقة التقليدية
    # ==========================================
    path(
        "<int:pk>/delete/",
        views.employee_delete_view,
        name="delete",
    ),

    # ==========================================
    # تصدير الموظفين إلى Excel
    # ==========================================
    path(
        "export/excel/",
        views.export_employees_excel,
        name="export-excel",
    ),

    # ==========================================
    # تفعيل / تعطيل موظف عبر AJAX
    # ==========================================
    path(
        "<int:pk>/toggle/ajax/",
        views.employee_toggle_active_ajax_view,
        name="toggle-active-ajax",
    ),

    # ==========================================
    # الحذف الآمن عبر AJAX
    # ==========================================
    path(
        "<int:pk>/delete/ajax/",
        views.employee_delete_ajax_view,
        name="delete-ajax",
    ),

]