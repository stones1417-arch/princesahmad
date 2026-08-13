from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from apps.core.middleware import OperationalSectionMiddleware
from apps.roles.models import Role, UserRole

User = get_user_model()


class OperationalSectionEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="section-context-user",
            password="StrongPassword123!",
        )
        self.endpoint = reverse("core:set-operational-section")

    def test_authenticated_user_choice_persists_in_session(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.endpoint,
            {"section": "female", "next": reverse("health-check")},
        )

        self.assertRedirects(response, reverse("health-check"))
        self.assertEqual(self.client.session["operational_section"], "female")

    def test_guest_cannot_store_a_concrete_operational_section(self):
        response = self.client.post(self.endpoint, {"section": "male"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertNotIn("operational_section", self.client.session)

    def test_middleware_exposes_the_session_section_to_views(self):
        request = RequestFactory().get("/hr/")
        request.user = self.user
        request.session = {"operational_section": "male"}
        captured_section = {}

        def get_response(current_request):
            captured_section["value"] = current_request.GET["section"]
            return HttpResponse()

        OperationalSectionMiddleware(get_response)(request)

        self.assertEqual(captured_section["value"], "male")

    def test_middleware_rejects_all_for_a_single_section_role(self):
        role = Role.objects.create(
            code="male-section-context",
            name="دور رجالي للسياق",
            group=Group.objects.create(name="male-section-context"),
            operational_section=Role.OperationalSection.MALE,
        )
        UserRole.objects.create(user=self.user, role=role)
        request = RequestFactory().get("/hr/?section=all")
        request.user = self.user
        request.session = {}
        captured_section = {}

        def get_response(current_request):
            captured_section["value"] = current_request.GET["section"]
            return HttpResponse()

        OperationalSectionMiddleware(get_response)(request)

        self.assertEqual(captured_section["value"], "male")

    def test_middleware_does_not_inject_section_for_admin_paths(self):
        request = RequestFactory().get("/admin/auth/user/")
        request.user = self.user
        request.session = {}
        captured_section = {}

        def get_response(current_request):
            captured_section["value"] = current_request.GET.get("section")
            return HttpResponse()

        OperationalSectionMiddleware(get_response)(request)

        self.assertIsNone(captured_section["value"])

    def test_useradmin_changelist_with_middleware_does_not_raise_lookup_error(self):
        request = RequestFactory().get("/admin/auth/user/")
        request.user = self.user
        request.user.is_staff = True
        request.user.is_superuser = True
        request.user.save(update_fields=["is_staff", "is_superuser"])
        request.session = {}

        def get_response(current_request):
            changelist = UserAdmin(User, admin.site).get_changelist_instance(current_request)
            self.assertIsNone(current_request.GET.get("section"))
            self.assertIsNotNone(changelist)
            return HttpResponse()

        response = OperationalSectionMiddleware(get_response)(request)

        self.assertEqual(response.status_code, 200)