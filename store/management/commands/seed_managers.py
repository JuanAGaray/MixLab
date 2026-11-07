from django.core.management.base import BaseCommand

from store.managers_services import seed_default_catalog


class Command(BaseCommand):
    help = 'Inicializa categorías, plantillas y perfiles de MixLab Managers.'

    def handle(self, *args, **options):
        result = seed_default_catalog()
        self.stdout.write(self.style.SUCCESS(
            f"Managers listo: {result['categories']} categorías, "
            f"{result['templates_created']} plantillas nuevas."
        ))
