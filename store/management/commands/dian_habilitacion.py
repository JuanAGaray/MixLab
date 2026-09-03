"""Comando: habilitación DIAN SETP — evaluar, generar y enviar 50 documentos."""

from django.core.management.base import BaseCommand, CommandError

from store.dian.exceptions import DianError, DianValidationError
from store.dian.habilitacion import evaluate_habilitacion, habilitacion_summary
from store.dian.services.habilitacion_setp import generate_habilitacion_batch, submit_habilitacion_batch


class Command(BaseCommand):
    help = (
        'Habilitación DIAN SETP: evalúa requisitos, genera 30 FE + 10 NC + 10 ND, '
        'y opcionalmente envía el ZIP a la DIAN.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--evaluate',
            action='store_true',
            help='Solo evaluar documentación requerida (checklist)',
        )
        parser.add_argument(
            '--generate',
            action='store_true',
            help='Generar los 50 documentos XML + ZIP',
        )
        parser.add_argument(
            '--submit',
            action='store_true',
            help='Enviar ZIP a DIAN (SendTestSetAsync)',
        )
        parser.add_argument(
            '--no-sign',
            action='store_true',
            help='Generar sin firmar (si no hay certificado .p12)',
        )

    def handle(self, *args, **options):
        if options['generate']:
            self._generate(sign=not options['no_sign'])
            return
        if options['submit']:
            self._submit()
            return
        # Por defecto: evaluar
        self._evaluate()

    def _evaluate(self):
        summary = habilitacion_summary()
        self.stdout.write(self.style.MIGRATE_HEADING('=== Habilitación DIAN SETP — Documentación requerida ==='))
        self.stdout.write('')
        for check in summary['checks']:
            icon = '[OK]' if check.ok else '[--]'
            if check.ok:
                icon = self.style.SUCCESS(icon)
            else:
                icon = self.style.ERROR(icon)
            req = '' if check.required else ' (opcional)'
            self.stdout.write(f'  {icon} {check.label}{req}')
            if check.detail:
                self.stdout.write(f'      > {check.detail}')
        self.stdout.write('')
        self.stdout.write(f"Progreso: {summary['passed']}/{summary['total']} verificaciones OK")
        if summary['ready_to_submit']:
            self.stdout.write(self.style.SUCCESS('Listo para enviar a DIAN: python manage.py dian_habilitacion --submit'))
        elif summary['ready_to_generate']:
            self.stdout.write(self.style.WARNING('Falta generar documentos: python manage.py dian_habilitacion --generate'))
        else:
            self.stdout.write(self.style.ERROR('Complete la configuración antes de generar.'))

    def _generate(self, *, sign: bool):
        try:
            batch = generate_habilitacion_batch(sign=sign)
        except (DianValidationError, DianError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f'Lote #{batch.pk} generado: {batch.invoice_count} FE, '
            f'{batch.credit_note_count} NC, {batch.debit_note_count} ND'
        ))
        if batch.zip_file:
            self.stdout.write(f'ZIP: {batch.zip_file.name}')
        self.stdout.write('Ejecute --evaluate para verificar o --submit para enviar a DIAN.')

    def _submit(self):
        try:
            result = submit_habilitacion_batch()
        except (DianValidationError, DianError) as exc:
            raise CommandError(str(exc)) from exc
        if result.get('success'):
            self.stdout.write(self.style.SUCCESS(f"Enviado. Track ID: {result.get('track_id', '—')}"))
        else:
            self.stdout.write(self.style.ERROR(f"DIAN: {result.get('message', 'Error')}"))
            self.stdout.write(result.get('raw_response', '')[:1000])
