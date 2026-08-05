from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Final

from locust import FastHttpUser, between, events, task


# ==========================================================
# الإعدادات
# ==========================================================


@dataclass(frozen=True)
class PerformanceSettings:
    """
    إعدادات اختبار الأداء.

    يفضّل تمرير اسم المستخدم وكلمة المرور
    من متغيرات البيئة بدل كتابتهما مباشرة.
    """

    username: str
    password: str

    login_path: str = "/accounts/login/"
    dashboard_path: str = "/"

    request_timeout: float = 30.0

    max_failure_ratio: float = 0.01
    max_average_response_ms: float = 1500.0
    max_p95_response_ms: float = 3000.0


SETTINGS: Final = PerformanceSettings(
    username=os.getenv(
        "PERF_USERNAME",
        "performance_admin",
    ),
    password=os.getenv(
        "PERF_PASSWORD",
        "ChangeThisPassword123!",
    ),
)


# ==========================================================
# CSRF
# ==========================================================


CSRF_PATTERN: Final = re.compile(
    r'name=["\']csrfmiddlewaretoken["\']'
    r'\s+value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def extract_csrf_token(
    html: str,
) -> str:
    """
    استخراج رمز CSRF من صفحة تسجيل الدخول.
    """

    match = CSRF_PATTERN.search(
        html or ""
    )

    if not match:
        return ""

    return match.group(1)


# ==========================================================
# مستخدم الاختبار
# ==========================================================


class AbwabPerformanceUser(FastHttpUser):
    """
    مستخدم افتراضي يحاكي الاستخدام اليومي لمنصة أبواب.
    """

    wait_time = between(
        1.0,
        3.0,
    )

    def on_start(self) -> None:
        """
        تسجيل الدخول عند بدء المستخدم الافتراضي.
        """

        self.login()

    def login(self) -> None:
        """
        تنفيذ تسجيل دخول حقيقي مع دعم CSRF.
        """

        with self.client.get(
            SETTINGS.login_path,
            name="auth_login_page",
            timeout=SETTINGS.request_timeout,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    "تعذر فتح صفحة تسجيل الدخول: "
                    f"{response.status_code}"
                )
                return

            csrf_token = extract_csrf_token(
                response.text
            )

            if not csrf_token:
                csrf_token = self.client.cookies.get(
                    "csrftoken",
                    "",
                )

            if not csrf_token:
                response.failure(
                    "لم يتم العثور على رمز CSRF."
                )
                return

        headers = {
            "Referer": (
                f"{self.host}"
                f"{SETTINGS.login_path}"
            ),
            "X-CSRFToken": csrf_token,
        }

        payload = {
            "username": SETTINGS.username,
            "password": SETTINGS.password,
            "csrfmiddlewaretoken": csrf_token,
            "next": SETTINGS.dashboard_path,
        }

        with self.client.post(
            SETTINGS.login_path,
            data=payload,
            headers=headers,
            name="auth_login_submit",
            timeout=SETTINGS.request_timeout,
            allow_redirects=True,
            catch_response=True,
        ) as response:
            if response.status_code not in {
                200,
                302,
            }:
                response.failure(
                    "فشل تسجيل الدخول: "
                    f"{response.status_code}"
                )
                return

            final_url = str(
                response.url or ""
            )

            if SETTINGS.login_path in final_url:
                response.failure(
                    "بقي المستخدم داخل صفحة تسجيل الدخول."
                )
                return

            response.success()

    def get_page(
        self,
        *,
        path: str,
        name: str,
    ) -> None:
        """
        تنفيذ طلب GET والتحقق من النتيجة.
        """

        with self.client.get(
            path,
            name=name,
            timeout=SETTINGS.request_timeout,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
                return

            if response.status_code == 302:
                redirect_location = (
                    response.headers.get(
                        "Location",
                        "",
                    )
                )

                if "login" in redirect_location:
                    response.failure(
                        "تم تحويل المستخدم إلى تسجيل الدخول."
                    )
                    return

            if response.status_code == 403:
                response.failure(
                    f"لا توجد صلاحية للوصول إلى: {path}"
                )
                return

            if response.status_code == 404:
                response.failure(
                    f"المسار غير موجود: {path}"
                )
                return

            if response.status_code >= 500:
                response.failure(
                    "خطأ خادم في المسار "
                    f"{path}: {response.status_code}"
                )
                return

            response.failure(
                "رمز استجابة غير متوقع في "
                f"{path}: {response.status_code}"
            )

    # ======================================================
    # المهام الأكثر استخدامًا
    # ======================================================

    @task(12)
    def dashboard(self) -> None:
        """
        فتح لوحة التحكم الرئيسية.
        """

        self.get_page(
            path="/",
            name="dashboard",
        )

    @task(10)
    def doors(self) -> None:
        """
        فتح لوحة الأبواب.
        """

        self.get_page(
            path="/ops/doors/",
            name="operations_doors",
        )

    @task(7)
    def maintenance(self) -> None:
        """
        فتح قائمة طلبات الصيانة.
        """

        self.get_page(
            path="/ops/maintenance/",
            name="maintenance_list",
        )

    @task(6)
    def incidents(self) -> None:
        """
        فتح قائمة البلاغات.
        """

        self.get_page(
            path="/ops/incidents/",
            name="incidents_list",
        )

    @task(5)
    def employees(self) -> None:
        """
        فتح قائمة الموظفين.
        """

        self.get_page(
            path="/hr/",
            name="employees_list",
        )

    @task(5)
    def reports(self) -> None:
        """
        فتح قائمة التقارير.
        """

        self.get_page(
            path="/reporting/",
            name="reports_list",
        )

    @task(4)
    def breaks(self) -> None:
        """
        فتح قائمة الراحات.
        """

        self.get_page(
            path="/breaks/",
            name="breaks_list",
        )

    @task(3)
    def notifications(self) -> None:
        """
        فتح الإشعارات.
        """

        self.get_page(
            path="/notifications/",
            name="notifications_list",
        )

    @task(2)
    def communications(self) -> None:
        """
        فتح التعاميم.
        """

        self.get_page(
            path="/communications/",
            name="communications_list",
        )

    @task(2)
    def exports_center(self) -> None:
        """
        فتح مركز التصدير.
        """

        self.get_page(
            path="/exports-center/",
            name="exports_center",
        )

    @task(1)
    def audit(self) -> None:
        """
        فتح سجل التدقيق.
        """

        self.get_page(
            path="/audit/",
            name="audit_history",
        )


# ==========================================================
# تقييم النتيجة النهائية
# ==========================================================


@events.quitting.add_listener
def evaluate_test_result(
    environment,
    **_kwargs,
) -> None:
    """
    إرجاع رمز فشل عند تجاوز الحدود المعتمدة.
    """

    stats = environment.stats.total

    failure_ratio = float(
        stats.fail_ratio or 0.0
    )

    average_response_time = float(
        stats.avg_response_time or 0.0
    )

    p95_response_time = float(
        stats.get_response_time_percentile(
            0.95
        )
        or 0.0
    )

    failures: list[str] = []

    if (
        failure_ratio
        > SETTINGS.max_failure_ratio
    ):
        failures.append(
            "نسبة الأخطاء تجاوزت "
            f"{SETTINGS.max_failure_ratio * 100:.0f}%."
        )

    if (
        average_response_time
        > SETTINGS.max_average_response_ms
    ):
        failures.append(
            "متوسط زمن الاستجابة تجاوز "
            f"{SETTINGS.max_average_response_ms:.0f}ms."
        )

    if (
        p95_response_time
        > SETTINGS.max_p95_response_ms
    ):
        failures.append(
            "زمن P95 تجاوز "
            f"{SETTINGS.max_p95_response_ms:.0f}ms."
        )

    print()
    print("=" * 60)
    print("ملخص تقييم أداء منصة أبواب")
    print("=" * 60)
    print(
        "نسبة الأخطاء: "
        f"{failure_ratio * 100:.2f}%"
    )
    print(
        "متوسط زمن الاستجابة: "
        f"{average_response_time:.2f}ms"
    )
    print(
        "زمن P95: "
        f"{p95_response_time:.2f}ms"
    )

    if failures:
        environment.process_exit_code = 1

        print("النتيجة: فشل")

        for failure in failures:
            print(
                f"- {failure}"
            )

    else:
        environment.process_exit_code = 0
        print("النتيجة: نجاح")

    print("=" * 60)