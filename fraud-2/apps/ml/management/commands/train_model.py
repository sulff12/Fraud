from django.core.management.base import BaseCommand

from apps.ml.services import train_models


class Command(BaseCommand):
    help = 'Train all candidate models and save the best artifact'

    def handle(self, *args, **options):
        result = train_models()
        self.stdout.write(self.style.SUCCESS(f"Best model: {result['best_model_name']}"))
        self.stdout.write(str(result))
