from django.contrib import admin
from .models import Zone, Door


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Door)
class DoorAdmin(admin.ModelAdmin):
    list_display = ('name', 'zone', 'is_active')
    list_filter = ('zone', 'is_active')
    search_fields = ('name',)
