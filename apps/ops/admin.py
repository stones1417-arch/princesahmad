from django.contrib import admin
from .models import DoorStatus, MaintenanceRequest


@admin.register(DoorStatus)
class DoorStatusAdmin(admin.ModelAdmin):
    list_display = ('door', 'shift_plan', 'status', 'timestamp')
    list_filter = ('status', 'shift_plan')


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = ('door', 'created_at', 'resolved')
    list_filter = ('resolved',)
