from django.core.management.base import BaseCommand

from apps.ml.services import score_transactions


class Command(BaseCommand):
    help = 'Score transactions using the active model artifact'

    def add_arguments(self, parser):
        parser.add_argument('--only-unscored', action='store_true', help='Score only rows with NULL fraud_probability')

    def handle(self, *args, **options):
        result = score_transactions(rescore_all=not options['only_unscored'])
        self.stdout.write(self.style.SUCCESS(f"Scored {result['scored_rows']} rows"))
        self.stdout.write(str(result))
