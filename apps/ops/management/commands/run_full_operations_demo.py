from django.core.management.base import BaseCommand
from ._full_operations_demo import production_guard, run_scenario, validate

class Command(BaseCommand):
    help = "Run a repeatable full operations demo scenario."
    def add_arguments(self, parser):
        parser.add_argument("--scenario", choices=["baseline", "incident-maintenance", "supervisory", "full-cycle"], default="full-cycle")
        parser.add_argument("--stop-before-final-close", action="store_true", default=True)
        parser.add_argument("--complete-final-close", action="store_false", dest="stop_before_final_close")
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-production-demo", action="store_true")
        parser.add_argument("--confirm-demo-seed", action="store_true")
    def handle(self, *args, **options):
        if options["validate_only"]:
            data, errors = validate(); self.stdout.write(str(data))
            if errors: from django.core.management.base import CommandError; raise CommandError("; ".join(errors))
            return
        production_guard(options)
        self.stdout.write(str(run_scenario(scenario=options["scenario"], stop_before_final_close=options["stop_before_final_close"], dry_run=options["dry_run"])))
