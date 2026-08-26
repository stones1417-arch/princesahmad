from django.core.management.base import BaseCommand
from ._full_operations_demo import production_guard, seed

class Command(BaseCommand):
    help = "Seed the safely marked full operations demo."
    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-production-demo", action="store_true")
        parser.add_argument("--confirm-demo-seed", action="store_true")
        parser.add_argument("--enable-demo-logins", action="store_true")
    def handle(self, *args, **options):
        production_guard(options)
        self.stdout.write(str(seed(dry_run=options["dry_run"], enable_demo_logins=options["enable_demo_logins"])))
