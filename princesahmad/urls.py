from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from apps.core.health import health_check


urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("", include("apps.core.urls")),
    # ==========================================================
    # لوحة التحكم الرئيسية
    # ==========================================================

    path(
        "",
        include("apps.dashboard.urls"),
    ),

    # ==========================================================
    # إدارة Django
    # ==========================================================

    path(
        "admin/",
        admin.site.urls,
    ),

    # ==========================================================
    # الحسابات والمصادقة
    # ==========================================================

    path(
        "accounts/",
        include("apps.accounts.urls"),
    ),

    path(
        "roles/",
        include("apps.roles.urls"),
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(
            next_page="/accounts/login/",
        ),
        name="logout",
    ),

    # ==========================================================
    # الموارد البشرية والمواقع
    # ==========================================================

    path(
        "hr/",
        include("apps.hr.urls"),
    ),

    path(
        "locations/",
        include("apps.locations.urls"),
    ),

    # ==========================================================
    # الورديات والتوزيع والراحات
    # ==========================================================

    path(
        "scheduling/",
        include("apps.scheduling.urls"),
    ),

    path(
        "distribution/",
        include("apps.distribution.urls"),
    ),

    path(
        "breaks/",
        include("apps.breaks.urls"),
    ),

    # ==========================================================
    # العمليات
    # ==========================================================

    path(
        "ops/",
        include("apps.ops.urls"),
    ),

    # ==========================================================
    # التعاميم والتقارير والتصدير
    # ==========================================================

    path(
        "communications/",
        include("apps.communications.urls"),
    ),

    path(
        "reporting/",
        include("apps.reporting.urls"),
    ),

    path(
        "exports/",
        include("apps.exports_center.urls"),
    ),

    # ==========================================================
    # الإشعارات
    # ==========================================================

    path(
        "notifications/",
        include("apps.notifications.urls"),
    ),

    # ==========================================================
    # سجل المراجعة والتدقيق
    # ==========================================================

    path(
        "audit/",
        include("apps.audit.urls"),
    ),
]


# ==========================================================
# ملفات الوسائط أثناء التطوير فقط
# ==========================================================

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
