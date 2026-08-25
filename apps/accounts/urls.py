from django.urls import path

from . import views


app_name = "accounts"


urlpatterns = [
    path("registration-requests/", views.registration_request_list, name="registration-request-list"),
    path("registration-requests/<int:pk>/", views.registration_request_review, name="registration-request-review"),
    path("registration-requests/<int:pk>/approve/", views.registration_request_approve, name="registration-request-approve"),
    path("registration-requests/<int:pk>/reject/", views.registration_request_reject, name="registration-request-reject"),
    path("registration-requests/<int:pk>/resend/", views.registration_request_resend, name="registration-request-resend"),
    path("activate/<uid>/<token>/", views.activate_account, name="activate"),
    path(
        "login/",
        views.login_view,
        name="login",
    ),

    path(
        "two-factor/",
        views.two_factor_view,
        name="two-factor",
    ),

    path(
        "admin/users/create/",
        views.admin_user_create_view,
        name="admin-user-create",
    ),

    path(
        "register/",
        views.register_view,
        name="register",
    ),

    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),

    path(
        "profile/",
        views.profile_view,
        name="profile",
    ),

    path(
        "password-change/",
        views.password_change_view,
        name="password-change",
    ),
]
