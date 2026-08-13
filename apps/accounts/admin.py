from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils import timezone

from apps.accounts.security import has_completed_two_factor
from apps.accounts.services.registration_request_service import (
    approve_account_registration_request,
)
from apps.hr.models import Employee
from apps.roles.models import Role
from apps.roles.services.access_control import user_has_permission
from apps.roles.services.permission_registry import PlatformPermissions

from .models import AccountRegistrationRequest, TwoFactorAuditLog


class AccountRegistrationRequestReviewForm(forms.ModelForm):
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        required=False,
        label="الدور",
    )
    operational_section = forms.ChoiceField(
        choices=[
            ("", "اختر القسم"),
            (Employee.OperationalSection.MALE, "رجالي"),
            (Employee.OperationalSection.FEMALE, "نسائي"),
        ],
        required=False,
        label="القسم التشغيلي",
    )

    class Meta:
        model = AccountRegistrationRequest
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].disabled = True
        self.fields["status"].widget.attrs["readonly"] = True
        self.fields["status"].required = False

        role_queryset = Role.objects.filter(is_active=True).order_by("name")
        self.fields["role"].queryset = role_queryset

        default_section = Employee.OperationalSection.MALE
        if getattr(self.instance, "gender", None) == AccountRegistrationRequest.Gender.FEMALE:
            default_section = Employee.OperationalSection.FEMALE

        self.fields["operational_section"].initial = default_section
        self.fields["operational_section"].widget.attrs["data-default-section"] = default_section

        matching_roles = role_queryset.filter(
            operational_section__in=[
                Role.OperationalSection.ALL,
                default_section,
            ]
        )
        if matching_roles.exists():
            self.fields["role"].initial = matching_roles.first().pk


@admin.register(AccountRegistrationRequest)
class AccountRegistrationRequestAdmin(admin.ModelAdmin):
    form = AccountRegistrationRequestReviewForm
    change_form_template = "admin/accounts/accountregistrationrequest/change_form.html"
    list_display = (
        "full_name",
        "employee_number",
        "requested_username",
        "email",
        "phone_number",
        "gender",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("status", "gender", "created_at", "reviewed_at")
    search_fields = (
        "full_name",
        "employee_number",
        "requested_username",
        "email",
        "phone_number",
    )
    readonly_fields = (
        "status",
        "created_at",
        "updated_at",
        "created_user",
        "linked_employee",
        "reviewed_by",
        "reviewed_at",
    )
    ordering = ("-created_at",)

    def _has_review_access(self, request):
        return bool(
            request.user.is_authenticated
            and request.user.is_staff
            and user_has_permission(request.user, PlatformPermissions.MANAGE_USERS)
            and has_completed_two_factor(request, request.user)
        )

    def _review_status_options(self, obj=None):
        return (
            AccountRegistrationRequest.Status.PENDING,
            AccountRegistrationRequest.Status.NEEDS_EDIT,
        )

    def _current_review_role(self, request, obj=None):
        selected_role = request.POST.get("role") or request.GET.get("role")
        if selected_role:
            return Role.objects.filter(pk=selected_role, is_active=True).first()
        if obj and obj.pk:
            return Role.objects.filter(is_active=True).order_by("name").first()
        return Role.objects.filter(is_active=True).order_by("name").first()

    def _current_review_section(self, request, obj=None):
        selected = request.POST.get("operational_section") or request.GET.get("operational_section")
        if selected in {Employee.OperationalSection.MALE, Employee.OperationalSection.FEMALE}:
            return selected
        if obj and getattr(obj, "gender", None) == AccountRegistrationRequest.Gender.FEMALE:
            return Employee.OperationalSection.FEMALE
        return Employee.OperationalSection.MALE

    def has_module_permission(self, request):
        return self._has_review_access(request)

    def has_view_permission(self, request, obj=None):
        return self._has_review_access(request)

    def has_change_permission(self, request, obj=None):
        return self._has_review_access(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        previous_status = None
        if obj.pk:
            previous_status = AccountRegistrationRequest.objects.filter(pk=obj.pk).values_list("status", flat=True).first()

        if (
            previous_status is not None
            and previous_status != obj.status
            and obj.status == AccountRegistrationRequest.Status.APPROVED
        ):
            raise ValidationError("لا يمكن اعتماد الطلب مباشرة من خلال الحفظ العادي. استخدم زر الاعتماد الرسمي.")

        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="accounts_accountregistrationrequest_approve",
            ),
            path(
                "<path:object_id>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="accounts_accountregistrationrequest_reject",
            ),
            path(
                "<path:object_id>/needs-edit/",
                self.admin_site.admin_view(self.needs_edit_view),
                name="accounts_accountregistrationrequest_needs_edit",
            ),
        ]
        return custom_urls + urls

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        response = super().changeform_view(
            request,
            object_id=object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

        if object_id is None:
            return response

        obj = get_object_or_404(AccountRegistrationRequest, pk=object_id)
        review_roles = Role.objects.filter(is_active=True).order_by("name")
        review_sections = [
            (Employee.OperationalSection.MALE, "رجالي"),
            (Employee.OperationalSection.FEMALE, "نسائي"),
        ]

        if hasattr(response, "context_data"):
            context = response.context_data
            context["review_roles"] = review_roles
            context["review_sections"] = review_sections
            context["selected_review_role"] = self._current_review_role(request, obj).pk if self._current_review_role(request, obj) else ""
            context["selected_review_section"] = self._current_review_section(request, obj)
            context["can_review_actions"] = (
                self._has_review_access(request)
                and obj.status in self._review_status_options(obj)
            )
            context["is_approved_request"] = obj.status == AccountRegistrationRequest.Status.APPROVED
        return response

    def approve_view(self, request, object_id):
        if request.method != "POST":
            raise PermissionDenied("طريقة الطلب غير مسموحة.")

        if not self._has_review_access(request):
            raise PermissionDenied("لا تملك صلاحية اعتماد طلبات إنشاء الحساب.")

        registration_request = get_object_or_404(AccountRegistrationRequest, pk=object_id)
        if registration_request.status not in self._review_status_options(registration_request):
            messages.error(request, "لا يمكن اعتماد طلب غير مفتوح للمراجعة.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        role_id = request.POST.get("role")
        selected_section = request.POST.get("operational_section")

        if not role_id:
            messages.error(request, "يجب اختيار الدور قبل الاعتماد.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        if selected_section not in {
            Employee.OperationalSection.MALE,
            Employee.OperationalSection.FEMALE,
        }:
            messages.error(request, "يجب تحديد القسم التشغيلي قبل الاعتماد.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        role = Role.objects.filter(pk=role_id, is_active=True).first()
        if role is None:
            messages.error(request, "الدور المختار غير صالح.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        if role.operational_section != Role.OperationalSection.ALL:
            if role.operational_section != selected_section:
                messages.error(request, "لا يتوافق نطاق الدور المختار مع القسم التشغيلي المحدد.")
                return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        try:
            approve_account_registration_request(registration_request, reviewer=request.user)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        messages.success(request, "تم اعتماد الطلب وإنشاء الحساب بنجاح.")
        return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

    def reject_view(self, request, object_id):
        if request.method != "POST":
            raise PermissionDenied("طريقة الطلب غير مسموحة.")

        if not self._has_review_access(request):
            raise PermissionDenied("لا تملك صلاحية مراجعة طلبات إنشاء الحساب.")

        registration_request = get_object_or_404(AccountRegistrationRequest, pk=object_id)
        if registration_request.status == AccountRegistrationRequest.Status.APPROVED:
            messages.error(request, "لا يمكن رفض طلب تم اعتماده بالفعل.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        registration_request.status = AccountRegistrationRequest.Status.REJECTED
        registration_request.reviewed_by = request.user
        registration_request.reviewed_at = timezone.now()
        registration_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

        messages.success(request, "تم رفض طلب إنشاء الحساب.")
        return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

    def needs_edit_view(self, request, object_id):
        if request.method != "POST":
            raise PermissionDenied("طريقة الطلب غير مسموحة.")

        if not self._has_review_access(request):
            raise PermissionDenied("لا تملك صلاحية مراجعة طلبات إنشاء الحساب.")

        registration_request = get_object_or_404(AccountRegistrationRequest, pk=object_id)
        if registration_request.status == AccountRegistrationRequest.Status.APPROVED:
            messages.error(request, "لا يمكن تحويل طلب تم اعتماده إلى يحتاج مراجعة.")
            return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

        registration_request.status = AccountRegistrationRequest.Status.NEEDS_EDIT
        registration_request.reviewed_by = request.user
        registration_request.reviewed_at = timezone.now()
        registration_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

        messages.success(request, "تم تحديث الطلب إلى يحتاج مراجعة.")
        return redirect("admin:accounts_accountregistrationrequest_change", object_id=registration_request.pk)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            status_priority=Case(
                When(status=AccountRegistrationRequest.Status.PENDING, then=Value(0)),
                When(status=AccountRegistrationRequest.Status.NEEDS_EDIT, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("status_priority", "-created_at")


@admin.register(TwoFactorAuditLog)
class TwoFactorAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "channel", "status", "ip_address", "created_at")
    list_filter = ("event", "channel", "status")
    search_fields = ("user__username",)
    readonly_fields = tuple(field.name for field in TwoFactorAuditLog._meta.fields)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"}

    def has_delete_permission(self, request, obj=None):
        return False
