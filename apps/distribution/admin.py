from django.contrib import admin
from .models import DoorAssignment


@admin.register(DoorAssignment)
class DoorAssignmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'door', 'shift_plan', 'is_supervisor')
    list_filter = ('shift_plan', 'door', 'is_supervisor')
