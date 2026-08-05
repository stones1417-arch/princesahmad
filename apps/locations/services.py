from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.core.notification_service import NotificationService
from apps.core.services import BaseService
from apps.dashboard.models import SystemActivityLog

from .models import Door, Zone


OFFICIAL_ZONES = [
    "الغربية",
    "الشمالية",
    "الشرقية",
    "الجنوبية",
]


class LocationService(BaseService):
    module_name = "المواقع والأبواب"

    @classmethod
    def create_zone(cls, *, request, name: str, notes: str = ""):
        name = (name or "").strip()
        notes = (notes or "").strip()

        if not name:
            raise ValidationError("اسم المنطقة مطلوب")

        if name not in OFFICIAL_ZONES:
            raise ValidationError("المناطق المعتمدة فقط: الغربية، الشمالية، الشرقية، الجنوبية")

        if Zone.objects.filter(name=name).exists():
            raise ValidationError("المنطقة موجودة مسبقًا")

        with cls.atomic():
            zone = Zone.objects.create(
                name=name,
                notes=notes or "منطقة رسمية",
            )

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.CREATE,
                description=f"تم إنشاء المنطقة {zone.name}",
            )

            NotificationService.success(
                title="تم إنشاء منطقة",
                message=f"تم إنشاء المنطقة {zone.name}",
                user=request.user,
                url="/locations/",
            )

        return zone

    @classmethod
    def update_zone(cls, *, request, zone: Zone, name: str, notes: str = ""):
        name = (name or "").strip()
        notes = (notes or "").strip()

        if not name:
            raise ValidationError("اسم المنطقة مطلوب")

        if name not in OFFICIAL_ZONES:
            raise ValidationError("المناطق المعتمدة فقط: الغربية، الشمالية، الشرقية، الجنوبية")

        exists = Zone.objects.filter(name=name).exclude(pk=zone.pk).exists()

        if exists:
            raise ValidationError("اسم المنطقة مستخدم مسبقًا")

        with cls.atomic():
            zone.name = name
            zone.notes = notes or "منطقة رسمية"
            zone.save(update_fields=["name", "notes"])

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم تعديل المنطقة {zone.name}",
            )

            NotificationService.info(
                title="تم تعديل منطقة",
                message=f"تم تعديل المنطقة {zone.name}",
                user=request.user,
                url="/locations/",
            )

        return zone

    @classmethod
    def update_door(
        cls,
        *,
        request,
        door: Door,
        door_number: str,
        name: str,
        zone: Zone,
        notes: str = "",
    ):
        door_number = (door_number or "").strip()
        name = (name or "").strip()
        notes = (notes or "").strip()

        if not name:
            raise ValidationError("اسم الباب مطلوب")

        if door_number:
            if not door_number.isdigit():
                raise ValidationError("رقم الباب يجب أن يكون رقمًا صحيحًا")

            door_number_value = int(door_number)

            exists = (
                Door.objects
                .filter(door_number=door_number_value)
                .exclude(pk=door.pk)
                .exists()
            )

            if exists:
                raise ValidationError("رقم الباب مستخدم مسبقًا")
        else:
            door_number_value = None

        with cls.atomic():
            door.door_number = door_number_value
            door.name = name
            door.zone = zone
            door.notes = notes
            door.full_clean()
            door.save(
                update_fields=[
                    "door_number",
                    "name",
                    "zone",
                    "notes",
                ]
            )

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم تعديل بيانات الباب {door}",
            )

            NotificationService.info(
                title="تم تعديل بيانات باب",
                message=f"تم تعديل بيانات {door}",
                user=request.user,
                url="/locations/",
            )

        return door

    @classmethod
    def toggle_door_active(cls, *, request, door: Door):
        action_text = "تعطيل" if door.is_active else "تفعيل"

        with cls.atomic():
            door.is_active = not door.is_active
            door.save(update_fields=["is_active"])

            cls.log(
                request=request,
                action=SystemActivityLog.ActionType.UPDATE,
                description=f"تم {action_text} الباب {door}",
            )

            NotificationService.warning(
                title=f"تم {action_text} باب",
                message=f"تم {action_text} {door}",
                user=request.user,
                url="/locations/",
            )

        return door