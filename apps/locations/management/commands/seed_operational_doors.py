from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.locations.models import Door, Zone

OFFICIAL_ZONES = {
    "الجهة الجنوبية": ["1", "2", "3", "4", "5", "6B"],
    "الجهة الغربية": ["6A", "7", "8", "9", "10", "11", "12", "13", "14"],
    "الجهة الشمالية": ["15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27"],
    "الجهة الشرقية": ["28", "29", "30", "31", "32", "33", "34", "35"],
    "الجهة الجنوبية الشرقية": ["36", "37", "38", "39", "40", "41"],
}


class Command(BaseCommand):
    help = "Seed the official operational door master data without deleting existing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Display what would change without writing to the database.",
        )

    def _summarize_zone(self, zone_name: str):
        zone, created = Zone.objects.get_or_create(
            name=zone_name,
            defaults={"notes": "منطقة رسمية"},
        )

        if created:
            return zone, "Created"

        if zone.notes != "منطقة رسمية":
            zone.notes = "منطقة رسمية"
            zone.save(update_fields=["notes"])
            return zone, "Updated"

        return zone, "Unchanged"

    def _summarize_door(self, *, door_number: str, zone: Zone):
        door, created = Door.objects.get_or_create(
            door_number=door_number,
            defaults={
                "zone": zone,
                "name": f"باب {door_number}",
                "notes": f"باب {door_number} في {zone.name}",
                "is_active": True,
            },
        )

        if created:
            return door, "Created"

        updated = False
        if door.zone_id != zone.id:
            door.zone = zone
            updated = True
        if not door.name:
            door.name = f"باب {door_number}"
            updated = True
        if not door.notes:
            door.notes = f"باب {door_number} في {zone.name}"
            updated = True
        if door.is_active is not True:
            door.is_active = True
            updated = True
        if door.door_number != door_number:
            door.door_number = door_number
            updated = True

        if updated:
            door.save()
            return door, "Updated"

        return door, "Unchanged"

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        zone_stats = {"Created": 0, "Updated": 0, "Unchanged": 0}
        door_stats = {"Created": 0, "Updated": 0, "Unchanged": 0}

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no records will be written."))

        with transaction.atomic():
            for zone_name, door_numbers in OFFICIAL_ZONES.items():
                zone = Zone.objects.filter(name=zone_name).first()
                if dry_run:
                    if zone is None:
                        zone_stats["Created"] += 1
                    elif zone.notes != "منطقة رسمية":
                        zone_stats["Updated"] += 1
                    else:
                        zone_stats["Unchanged"] += 1

                    for door_number in door_numbers:
                        door = Door.objects.filter(door_number=door_number).first()
                        if door is None:
                            door_stats["Created"] += 1
                        else:
                            should_update = (
                                door.zone_id is not None and zone is not None and door.zone_id != zone.id
                            ) or (not door.name) or (not door.notes) or (door.is_active is not True)
                            if should_update:
                                door_stats["Updated"] += 1
                            else:
                                door_stats["Unchanged"] += 1
                    continue

                zone, zone_status = self._summarize_zone(zone_name)
                zone_stats[zone_status] += 1

                for door_number in door_numbers:
                    _, door_status = self._summarize_door(door_number=door_number, zone=zone)
                    door_stats[door_status] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Zones: Created={created} Updated={updated} Unchanged={unchanged}".format(
                    created=zone_stats["Created"],
                    updated=zone_stats["Updated"],
                    unchanged=zone_stats["Unchanged"],
                )
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Doors: Created={created} Updated={updated} Unchanged={unchanged}".format(
                    created=door_stats["Created"],
                    updated=door_stats["Updated"],
                    unchanged=door_stats["Unchanged"],
                )
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete: no database changes were written."))
