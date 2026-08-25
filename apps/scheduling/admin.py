from django.contrib import admin
from .models import ShiftType, ShiftPlan, ShiftAssignment, ShiftOperationalLeadership


@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(ShiftPlan)
class ShiftPlanAdmin(admin.ModelAdmin):
    list_display = ('date', 'shift_type')
    list_filter = ('shift_type', 'date')


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'shift_plan')
    list_filter = ('shift_plan',)


@admin.register(ShiftOperationalLeadership)
class ShiftOperationalLeadershipAdmin(admin.ModelAdmin):
    list_display = ("shift_plan", "responsibility", "employee")
    list_filter = ("responsibility", "shift_plan")
