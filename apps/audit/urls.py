from django.urls import path

from . import views


app_name = "audit"


urlpatterns = [

    # ==========================================================
    # الصفحة الرئيسية لسجل المراجعة
    # ==========================================================

    path(
        "",
        views.history_list_view,
        name="history-list",
    ),

    # ==========================================================
    # تفاصيل سجل تدقيق
    # ==========================================================

    path(
        "<str:model_type>/<int:pk>/",
        views.history_detail_view,
        name="history-detail",
    ),

]