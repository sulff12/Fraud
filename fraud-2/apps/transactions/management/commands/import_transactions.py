from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.transactions.services import import_transactions_from_csv


class Command(BaseCommand):
    help = 'Import normalized transaction CSV into the database'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        file_path = Path(options['file'])
        if not file_path.exists():
            raise CommandError(f'File not found: {file_path}')

        with file_path.open('rb') as fh:
            batch, rows = import_transactions_from_csv(fh, filename=file_path.name)
        self.stdout.write(self.style.SUCCESS(f'Imported {rows} rows from {batch.original_filename}'))
