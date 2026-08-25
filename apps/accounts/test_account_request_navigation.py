from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountRegistrationRequest
from apps.core.tests.factories import create_user
from apps.roles.models import Role
from apps.roles.services.role_manager import assign_role_to_user


class AccountRequestNavigationTests(TestCase):
    password = "Navigation-Test-987!"

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles")
        cls.reviewer = create_user(username="navigation-reviewer", password=cls.password, email="nav-reviewer@example.test")
        assign_role_to_user(user=cls.reviewer, role_code="system_admin")
        cls.outsider = create_user(username="navigation-outsider", password=cls.password, email="nav-outsider@example.test")
        cls.registration = AccountRegistrationRequest.objects.create(full_name="طلب تنقل", employee_number="NAV-001", requested_username="navigation-request", email="nav-request@example.test", phone_number="+966551234501", gender="male")

    def test_authorized_menu_targets_institutional_list_not_admin(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertContains(response, f'href="{reverse("accounts:registration-request-list")}"')
        self.assertNotContains(response, f'href="{reverse("admin:accounts_accountregistrationrequest_changelist")}"')
        self.assertContains(response, "admin-dropdown enterprise-nav-dropdown is-active")
        self.assertContains(response, "الإدارة")

    def test_unauthorized_menu_hidden_and_direct_routes_forbidden(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("dashboard:index")), reverse("accounts:registration-request-list"))
        self.assertEqual(self.client.get(reverse("accounts:registration-request-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:registration-request-review", args=[self.registration.pk])).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_list_review_link_stays_in_institutional_ui(self):
        self.client.force_login(self.reviewer)
        source = get_template("accounts/registration_request_list.html").template.source
        self.assertIn("accounts:registration-request-review", source)
        self.assertNotIn("admin:accounts_accountregistrationrequest_change", source)
        review_url = reverse("accounts:registration-request-review", args=[self.registration.pk])
        response = self.client.get(review_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مراجعة الطلب")

    def test_django_admin_fallback_remains_registered(self):
        self.assertEqual(reverse("admin:accounts_accountregistrationrequest_changelist"), "/admin/accounts/accountregistrationrequest/")

    def test_review_page_has_institutional_ui_contract(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(
            reverse("accounts:registration-request-review", args=[self.registration.pk]),
        )
        for text in (
            "مراجعة واعتماد طلب الحساب",
            "بيانات مقدم الطلب",
            "نتيجة التحقق",
            "التسكين والصلاحيات",
            "ملخص الاعتماد",
            "تأكيد اعتماد طلب الحساب",
            "رفض طلب إنشاء الحساب",
            "مراجعة الطلب #",
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'name="operational_section"')
        self.assertContains(response, 'name="role_code"')
        self.assertEqual(
            [card["role"] for card in response.context["role_cards"]],
            list(response.context["approval_form"].fields["role_code"].queryset),
        )

    def test_review_assets_are_responsive_and_use_no_native_dialogs(self):
        template = get_template("accounts/registration_request_review.html").template.source
        script = Path(settings.BASE_DIR, "static/js/accounts/registration_request_review.js").read_text(encoding="utf-8")
        stylesheet = Path(settings.BASE_DIR, "static/css/accounts/registration_request_review.css").read_text(encoding="utf-8")
        self.assertNotIn("window.confirm", script)
        self.assertNotIn("window.alert", script)
        self.assertNotIn("window.prompt", script)
        self.assertIn('aria-modal="true"', template)
        self.assertIn("data-submit-label", template)
        self.assertIn("@media(max-width:900px)", stylesheet)
        self.assertIn("@media(max-width:600px)", stylesheet)
        self.assertIn("overflow-wrap:anywhere", stylesheet)

    def test_awaiting_activation_and_email_failure_state(self):
        user = create_user(
            username="review-awaiting",
            password=None,
            email="review-awaiting@example.test",
            is_active=False,
        )
        self.registration.status = AccountRegistrationRequest.Status.APPROVED
        self.registration.created_user = user
        self.registration.operational_section = "male"
        self.registration.activation_email_error = "provider details must stay private"
        self.registration.save()
        self.client.force_login(self.reviewer)
        response = self.client.get(
            reverse("accounts:registration-request-review", args=[self.registration.pk]),
        )
        self.assertContains(response, "بانتظار التفعيل")
        self.assertContains(response, "تعذر إرسال رسالة التفعيل")
        self.assertContains(response, "إعادة إرسال رابط التفعيل")
        self.assertNotContains(response, self.registration.activation_email_error)
        self.assertNotContains(response, "اعتماد وإنشاء الحساب")

    def test_activated_state_hides_provisioning_actions(self):
        user = create_user(
            username="review-activated",
            password=self.password,
            email="review-activated@example.test",
            is_active=True,
        )
        self.registration.status = AccountRegistrationRequest.Status.ACTIVATED
        self.registration.created_user = user
        self.registration.operational_section = "male"
        self.registration.activated_at = timezone.now()
        self.registration.save()
        self.client.force_login(self.reviewer)
        response = self.client.get(
            reverse("accounts:registration-request-review", args=[self.registration.pk]),
        )
        self.assertContains(response, "الحساب مفعّل")
        self.assertContains(response, "تاريخ التفعيل")
        self.assertNotContains(response, "إعادة إرسال رابط التفعيل")
        self.assertNotContains(response, "رفض الطلب")

    def test_request_list_has_institutional_center_contract(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("accounts:registration-request-list"))
        for text in (
            "طلبات إنشاء الحساب",
            "إدارة الحسابات",
            "طلبات جديدة",
            "بانتظار التفعيل",
            "البحث والتصفية",
            "نتائج الطلبات",
            "مراجعة الطلب",
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'id="request-search"')
        self.assertContains(response, '<th scope="col">', count=7)
        self.assertContains(response, "account-requests-card")
        self.assertNotContains(response, reverse("admin:accounts_accountregistrationrequest_changelist"))

    def test_request_list_empty_state_and_filter_reset(self):
        AccountRegistrationRequest.objects.all().delete()
        self.client.force_login(self.reviewer)
        response = self.client.get(
            reverse("accounts:registration-request-list"),
            {"q": "missing"},
        )
        self.assertContains(response, "لا توجد طلبات إنشاء حساب حاليًا")
        self.assertContains(response, "إعادة ضبط الفلاتر")

    def test_request_list_lifecycle_badges_and_actions(self):
        active_user = create_user(
            username="list-active-state",
            password=self.password,
            email="list-active-state@example.test",
            is_active=True,
        )
        activated = AccountRegistrationRequest.objects.create(
            full_name="طلب مفعل",
            employee_number="LIST-ACTIVE",
            requested_username="list-active-state",
            email="list-active-state@example.test",
            phone_number="+966551234577",
            gender="male",
            status=AccountRegistrationRequest.Status.ACTIVATED,
            created_user=active_user,
            activated_at=timezone.now(),
        )
        rejected = AccountRegistrationRequest.objects.create(
            full_name="طلب مرفوض",
            employee_number="LIST-REJECTED",
            requested_username="list-rejected-state",
            email="list-rejected-state@example.test",
            phone_number="+966551234578",
            gender="male",
            status=AccountRegistrationRequest.Status.REJECTED,
        )
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertContains(response, "مفعّل")
        self.assertContains(response, "عرض التفاصيل")
        self.assertContains(response, "مرفوض")
        self.assertContains(response, reverse("accounts:registration-request-review", args=[activated.pk]))
        self.assertContains(response, reverse("accounts:registration-request-review", args=[rejected.pk]))

    def test_request_list_styles_cover_desktop_tablet_and_mobile(self):
        stylesheet = Path(settings.BASE_DIR, "static/css/accounts/registration_request_list.css").read_text(encoding="utf-8")
        self.assertIn("max-width:1560px", stylesheet)
        self.assertIn("@media(max-width:1180px)", stylesheet)
        self.assertIn("@media(max-width:760px)", stylesheet)
        self.assertIn(".account-requests-table{display:none}", stylesheet)
        self.assertIn("overflow-wrap:anywhere", stylesheet)


class AccountRequestListConsistencyTests(TestCase):
    password = "List-Consistency-987!"

    def setUp(self):
        call_command("setup_roles")
        self.reviewer = create_user(username="list-reviewer", password=self.password, email="list-reviewer@example.test")
        assign_role_to_user(user=self.reviewer, role_code="system_admin")
        self.client.force_login(self.reviewer)
        self.pending_male = AccountRegistrationRequest.objects.create(full_name="طلب رجالي جديد", employee_number="LIST-M-1", requested_username="list-male", email="list-male@example.test", phone_number="+966551234511", gender="male", operational_section="")
        self.pending_female = AccountRegistrationRequest.objects.create(full_name="طلب نسائي جديد", employee_number="LIST-F-1", requested_username="list-female", email="list-female@example.test", phone_number="+966551234512", gender="female", operational_section="female")
        awaiting_user = create_user(username="awaiting-user", password=None, email="awaiting@example.test", is_active=False)
        self.awaiting = AccountRegistrationRequest.objects.create(full_name="طلب بانتظار التفعيل", employee_number="LIST-M-2", requested_username="awaiting-user", email="awaiting@example.test", phone_number="+966551234513", gender="male", operational_section="male", status=AccountRegistrationRequest.Status.APPROVED, created_user=awaiting_user)

    def test_all_status_filter_has_no_hidden_status_constraint(self):
        response = self.client.get(reverse("accounts:registration-request-list"), {"status": "", "section": "male"})
        self.assertContains(response, self.pending_male.full_name)
        self.assertContains(response, self.awaiting.full_name)

    def test_pending_and_awaiting_activation_are_visible_and_labeled(self):
        response = self.client.get(reverse("accounts:registration-request-list"), {"section": "male"})
        self.assertContains(response, self.pending_male.full_name)
        self.assertContains(response, self.awaiting.full_name)
        self.assertContains(response, "بانتظار التفعيل")

    def test_male_and_female_filters_use_effective_request_section(self):
        male = self.client.get(reverse("accounts:registration-request-list"), {"section": "male"})
        self.assertContains(male, self.pending_male.full_name)
        self.assertNotContains(male, self.pending_female.full_name)
        female = self.client.get(reverse("accounts:registration-request-list"), {"section": "female"})
        self.assertContains(female, self.pending_female.full_name)
        self.assertNotContains(female, self.pending_male.full_name)

    def test_legacy_blank_section_falls_back_to_gender(self):
        response = self.client.get(reverse("accounts:registration-request-list"), {"section": "male"})
        self.assertContains(response, self.pending_male.full_name)

    def test_kpis_and_list_share_section_scope(self):
        response = self.client.get(reverse("accounts:registration-request-list"), {"section": "male"})
        self.assertEqual(response.context["kpis"]["pending"], 1)
        self.assertEqual(response.context["kpis"]["waiting"], 1)
        self.assertEqual(response.context["registration_requests"].count(), 2)

    def test_invalid_status_behaves_as_all_statuses(self):
        response = self.client.get(reverse("accounts:registration-request-list"), {"status": "all", "section": "male"})
        self.assertEqual(response.context["selected_status"], "")
        self.assertContains(response, self.pending_male.full_name)
        self.assertContains(response, self.awaiting.full_name)


class AccountRequestEffectiveSectionTests(TestCase):
    password = "Effective-Section-987!"

    def setUp(self):
        call_command("setup_roles")
        self.reviewer = create_user(
            username="section-reviewer",
            password=self.password,
            email="section-reviewer@example.test",
        )
        assign_role_to_user(user=self.reviewer, role_code="system_admin")
        self.client.force_login(self.reviewer)

    def set_reviewer_scope(self, section):
        Role.objects.filter(code="system_admin").update(operational_section=section)

    def create_request(self, suffix, *, gender, section="", status=None, user=None):
        values = {
            "full_name": f"Production shape {suffix}",
            "employee_number": f"SCOPE-{suffix}",
            "requested_username": f"scope-{suffix}",
            "email": f"scope-{suffix}@example.test",
            "phone_number": f"+96655123{suffix:04d}",
            "gender": gender,
            "operational_section": section,
            "created_user": user,
        }
        if status:
            values["status"] = status
        return AccountRegistrationRequest.objects.create(**values)

    def test_exact_production_male_shape_uses_user_scope_for_kpis_and_list(self):
        self.set_reviewer_scope(Role.OperationalSection.MALE)
        pending = self.create_request(101, gender="male")
        inactive_user = create_user(
            username="production-awaiting",
            password=None,
            email="production-awaiting@example.test",
            is_active=False,
        )
        awaiting = self.create_request(
            102,
            gender="male",
            status=AccountRegistrationRequest.Status.APPROVED,
            user=inactive_user,
        )

        response = self.client.get(reverse("accounts:registration-request-list"))

        self.assertEqual(response.context["selected_section"], "male")
        self.assertEqual(response.context["kpis"]["pending"], 1)
        self.assertEqual(response.context["kpis"]["waiting"], 1)
        self.assertQuerySetEqual(
            response.context["registration_requests"].order_by("pk"),
            [pending, awaiting],
        )
        self.assertContains(response, "بانتظار التفعيل")

    def test_blank_female_fallback_is_visible_in_female_scope(self):
        self.set_reviewer_scope(Role.OperationalSection.FEMALE)
        female = self.create_request(201, gender="female")
        response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertQuerySetEqual(response.context["registration_requests"], [female])
        self.assertEqual(response.context["kpis"]["pending"], 1)

    def test_fallback_section_scope_has_no_cross_section_leak(self):
        male = self.create_request(301, gender="male")
        female = self.create_request(302, gender="female")
        self.set_reviewer_scope(Role.OperationalSection.MALE)
        male_response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertQuerySetEqual(male_response.context["registration_requests"], [male])
        self.set_reviewer_scope(Role.OperationalSection.FEMALE)
        female_response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertQuerySetEqual(female_response.context["registration_requests"], [female])

    def test_explicit_section_takes_precedence_over_gender(self):
        request = self.create_request(401, gender="male", section="female")
        self.set_reviewer_scope(Role.OperationalSection.MALE)
        male_response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertNotContains(male_response, request.full_name)
        self.set_reviewer_scope(Role.OperationalSection.FEMALE)
        female_response = self.client.get(reverse("accounts:registration-request-list"))
        self.assertContains(female_response, request.full_name)

    def test_unclassified_request_is_hidden_from_section_scopes(self):
        request = self.create_request(501, gender="male")
        AccountRegistrationRequest.objects.filter(pk=request.pk).update(gender="")
        self.set_reviewer_scope(Role.OperationalSection.MALE)
        self.assertNotContains(
            self.client.get(reverse("accounts:registration-request-list")),
            request.full_name,
        )

        self.set_reviewer_scope(Role.OperationalSection.ALL)
        self.assertContains(
            self.client.get(
                reverse("accounts:registration-request-list"),
                {"section": ""},
            ),
            request.full_name,
        )
