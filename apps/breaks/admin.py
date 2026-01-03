from django.contrib import admin
from .models import Break


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'start_time', 'end_time')
