from django.urls import path

from . import views

app_name = "roles"

urlpatterns = [
    path("employee-assignment/", views.employee_assignment_view, name="employee-assignment"),
    path("<slug:code>/", views.role_detail_view, name="role-detail"),
]
