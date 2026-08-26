from django.core.management.base import BaseCommand, CommandError
from ._full_operations_demo import validate

class Command(BaseCommand):
    help = "Read-only validation for the full operations demo."
    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")
    def handle(self, *args, **options):
        data, errors = validate()
        self.stdout.write(str(data))
        if errors and options["strict"]: raise CommandError("; ".join(errors))
        if errors:
            self.stdout.write(self.style.WARNING("; ".join(errors)))
            return
        self.stdout.write(self.style.SUCCESS("Full operations demo is valid."))
