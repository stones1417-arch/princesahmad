from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # =========================
    # لوحة الإدارة
    # =========================
    path('admin/', admin.site.urls),

    # =========================
    # تطبيقات المنصة
    # =========================

    # الحسابات والصلاحيات
    path('accounts/', include('apps.accounts.urls')),

    # الموارد البشرية (الموظفين)
    path('hr/', include('apps.hr.urls')),

    # الأبواب والمناطق
    path('locations/', include('apps.locations.urls')),

    # الورديات والتسكين
    path('scheduling/', include('apps.scheduling.urls')),

    # توزيع الموظفين على الأبواب
    path('distribution/', include('apps.distribution.urls')),

    # الراحات
    path('breaks/', include('apps.breaks.urls')),

    # التشغيل اليومي (حالة الأبواب – الصيانة)
    path('ops/', include('apps.ops.urls')),

    # التعاميم
    path('communications/', include('apps.communications.urls')),

    # التقارير
    path('reporting/', include('apps.reporting.urls')),
]
