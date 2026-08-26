from django.core.management.base import BaseCommand, CommandError
from ._full_operations_demo import delete, production_guard

class Command(BaseCommand):
    help = "Delete only records owned by the full operations demo."
    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-production-demo", action="store_true")
        parser.add_argument("--confirm", action="store_true")
    def handle(self, *args, **options):
        if not options["dry_run"] and not options["confirm"]:
            raise CommandError("Deletion refused; pass --confirm explicitly.")
        production_guard(options, delete=True)
        self.stdout.write(str(delete(dry_run=options["dry_run"])))
