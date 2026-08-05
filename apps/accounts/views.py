from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from apps.hr.models import Employee

from .forms import ProfilePhotoForm
from .models import AccountProfile
from .security import clear_login_failures, login_is_limited, record_login_failure


def register_view(request):
    """
    إنشاء حساب مستخدم جديد وربطه بسجل موظف.
    """
    if request.user.is_authenticated:
        return redirect("dashboard:index")

    if not settings.ALLOW_PUBLIC_REGISTRATION:
        raise PermissionDenied("التسجيل العام غير متاح.")

    photo_form = ProfilePhotoForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        employee_number = (request.POST.get("employee_number") or "").strip()
        username = (request.POST.get("username") or "").strip().lower()
        password = request.POST.get("password") or ""
        job_title = (request.POST.get("job_title") or "").strip()

        context = {
            "job_title_choices": Employee.JobTitle.choices,
            "form_data": request.POST,
            "photo_form": photo_form,
        }

        if not all([full_name, employee_number, username, password, job_title]):
            messages.error(request, "أكمل جميع الحقول المطلوبة.")
            return render(request, "accounts/register.html", context)

        if job_title not in Employee.JobTitle.values:
            messages.error(request, "المسمى الوظيفي المحدد غير صالح.")
            return render(request, "accounts/register.html", context)

        try:
            validate_password(password, user=User(username=username))
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, "accounts/register.html", context)

        if not photo_form.is_valid():
            messages.error(request, "تعذر رفع الصورة. راجع الصيغة والحجم.")
            return render(request, "accounts/register.html", context)

        if User.objects.filter(username=username).exists():
            messages.error(request, "اسم المستخدم مستخدم مسبقًا.")
            return render(request, "accounts/register.html", context)

        if Employee.objects.filter(employee_number=employee_number).exists():
            messages.error(request, "الرقم الوظيفي مسجل مسبقًا.")
            return render(request, "accounts/register.html", context)

        try:
            with transaction.atomic():
                name_parts = full_name.split(maxsplit=1)
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=name_parts[0],
                    last_name=name_parts[1] if len(name_parts) > 1 else "",
                )
                Employee.objects.create(
                    user=user,
                    full_name=full_name,
                    employee_number=employee_number,
                    job_title=job_title,
                )
                AccountProfile.objects.create(
                    user=user,
                    photo=photo_form.cleaned_data.get("photo"),
                )
        except IntegrityError:
            messages.error(request, "اسم المستخدم أو الرقم الوظيفي مستخدم مسبقًا.")
            return render(request, "accounts/register.html", context)
        except Exception:
            messages.error(request, "حدث خطأ غير متوقع أثناء إنشاء الحساب.")
            return render(request, "accounts/register.html", context)

        messages.success(request, "تم إنشاء الحساب بنجاح، يمكنك تسجيل الدخول الآن.")
        return redirect("accounts:login")

    return render(request, "accounts/register.html", {
        "job_title_choices": Employee.JobTitle.choices,
        "photo_form": photo_form,
    })


def login_view(request):
    """
    تسجيل دخول المستخدم.
    """
    if request.user.is_authenticated:
        return redirect(
            "dashboard:index"
        )

    if request.method == "POST":
        username = (
            request.POST.get("username") or ""
        ).strip().lower()

        password = (
            request.POST.get("password") or ""
        )

        next_url = request.POST.get("next") or ""
        login_context = {
            "next": next_url,
            "entered_username": username,
        }

        if not username or not password:
            messages.error(request, "يرجى إدخال اسم المستخدم وكلمة المرور.")
            return render(request, "accounts/login.html", login_context)

        if login_is_limited(request, username):
            messages.error(
                request,
                "تم تعليق محاولات الدخول مؤقتًا. حاول لاحقًا.",
            )
            return render(request, "accounts/login.html", login_context, status=429)

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            if not user.is_active:
                messages.error(
                    request,
                    "هذا الحساب معطل.",
                )

                return render(request, "accounts/login.html", login_context)

            login(
                request,
                user,
            )

            clear_login_failures(request, username)

            if request.POST.get("remember_me") == "on":
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                request.session.set_expiry(0)

            messages.success(
                request,
                (
                    f"مرحبًا بك، "
                    f"{user.get_full_name() or user.username}."
                ),
            )

            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect(
                "dashboard:index"
            )

        record_login_failure(request, username)
        messages.error(
            request,
            "بيانات الدخول غير صحيحة.",
        )

        return render(request, "accounts/login.html", login_context)

    return render(
        request,
        "accounts/login.html",
        {
            "next": request.GET.get(
                "next",
                "",
            ),
        },
    )


@require_POST
@login_required
def logout_view(request):
    """
    تسجيل خروج المستخدم بطريقة آمنة عبر طلب POST.
    """
    username = (
        request.user.get_full_name()
        or request.user.username
    )

    auth_logout(request)

    messages.success(
        request,
        f"تم تسجيل خروج {username} بنجاح.",
    )

    return redirect(
        "accounts:login"
    )


@login_required
def profile_view(request):
    """
    عرض الملف الشخصي للمستخدم الحالي.
    """
    user = request.user

    account_profile, _ = AccountProfile.objects.get_or_create(
        user=user,
    )

    if request.method == "POST":
        photo_form = ProfilePhotoForm(
            request.POST,
            request.FILES,
            instance=account_profile,
        )
        if photo_form.is_valid():
            photo_form.save()
            messages.success(request, "تم تحديث الصورة الشخصية بنجاح.")
            return redirect("accounts:profile")
        messages.error(request, "تعذر تحديث الصورة. راجع الصيغة والحجم.")
    else:
        photo_form = ProfilePhotoForm(instance=account_profile)

    employee = (
        Employee.objects
        .filter(user=user)
        .first()
    )

    if user.is_superuser:
        account_role = "مدير النظام"

    elif user.is_staff:
        account_role = "موظف إداري"

    elif (
        employee
        and getattr(
            employee,
            "job_title",
            None,
        )
    ):
        try:
            account_role = (
                employee.get_job_title_display()
            )
        except (AttributeError, TypeError):
            account_role = "مستخدم"

    else:
        account_role = "مستخدم"

    full_name = (
        employee.full_name
        if (
            employee
            and employee.full_name
        )
        else (
            user.get_full_name()
            or user.username
        )
    )

    context = {
        "profile_user": user,
        "employee": employee,
        "full_name": full_name,
        "account_role": account_role,
        "account_profile": account_profile,
        "photo_form": photo_form,
    }

    return render(
        request,
        "accounts/profile.html",
        context,
    )


@login_required
def password_change_view(request):
    """
    تغيير كلمة مرور المستخدم الحالي
    مع الإبقاء على جلسة الدخول.
    """
    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST,
        )

        if form.is_valid():
            user = form.save()

            update_session_auth_hash(
                request,
                user,
            )

            messages.success(
                request,
                "تم تغيير كلمة المرور بنجاح.",
            )

            return redirect(
                "accounts:profile"
            )

        messages.error(
            request,
            (
                "تعذر تغيير كلمة المرور. "
                "راجع البيانات المدخلة."
            ),
        )

    else:
        form = PasswordChangeForm(
            user=request.user,
        )

    return render(
        request,
        "accounts/password_change.html",
        {
            "form": form,
        },
    )
