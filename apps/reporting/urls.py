from django.urls import path

from . import views


app_name = "reporting"


urlpatterns = [
    # قائمة التقارير
    path(
        "",
        views.report_list_view,
        name="list",
    ),

    # لوحة المؤشرات التنفيذية الشهرية
    path(
        "executive/monthly/",
        views.executive_monthly_dashboard_view,
        name="executive-monthly",
    ),

    # التقرير التشغيلي المباشر
    path(
        "operational/",
        views.operational_report_view,
        name="operational",
    ),

    # إنشاء تقرير جديد
    path(
        "create/",
        views.report_create_view,
        name="create",
    ),

    # إنشاء تقرير تشغيلي
    path(
        "create/operational/",
        views.report_create_view,
        {
            "default_report_type": "operational",
        },
        name="create-operational",
    ),

    # إنشاء تقرير يدوي
    path(
        "create/manual/",
        views.report_create_view,
        {
            "default_report_type": "manual",
        },
        name="create-manual",
    ),

    # توليد تقرير لوردية محددة
    path(
        "generate/<int:pk>/",
        views.generate_report_view,
        name="generate",
    ),

    # توليد تقرير للوردية النشطة
    path(
        "generate-active/",
        views.generate_active_shift_report_view,
        name="generate-active",
    ),

    # تفاصيل التقرير
    path(
        "<int:pk>/",
        views.report_detail_view,
        name="detail",
    ),

    # اعتماد التقرير
    path(
        "<int:pk>/approve/",
        views.approve_report_view,
        name="approve",
    ),

    # إعادة إنشاء المؤشرات والملخص
    path(
        "<int:pk>/regenerate-summary/",
        views.regenerate_report_summary_view,
        name="regenerate-summary",
    ),

    # تصدير التقرير إلى PDF
    path(
        "<int:pk>/export/pdf/",
        views.export_report_pdf_view,
        name="export-pdf",
    ),

    # تصدير التقرير إلى Excel
    path(
        "<int:pk>/export/excel/",
        views.export_report_excel_view,
        name="export-excel",
    ),

    # تحديث التقرير ثم تصديره إلى PDF
    path(
        "<int:pk>/refresh-export/pdf/",
        views.refresh_and_export_report_pdf_view,
        name="refresh-export-pdf",
    ),
]
