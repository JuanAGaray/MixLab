"""Comando: información de configuración DIAN / habilitación SETP."""

from django.core.management.base import BaseCommand

from store.dian.config import get_dian_config
from store.dian.habilitacion import evaluate_habilitacion
from store.dian.models import DianElectronicInvoice, DianHabilitacionBatch, DianInvoiceSequence


class Command(BaseCommand):
    help = 'Muestra configuración DIAN y estado de numeración SETP (habilitación).'

    def handle(self, *args, **options):
        cfg = get_dian_config()
        seq = DianInvoiceSequence.objects.filter(pk=1).first()
        fe_count = DianElectronicInvoice.objects.count()
        accepted = DianElectronicInvoice.objects.filter(status='accepted').count()
        batch = DianHabilitacionBatch.objects.order_by('-created_at').first()

        self.stdout.write('=== Configuración DIAN ===')
        self.stdout.write(f'Ambiente:       {cfg.environment}')
        self.stdout.write(f'Software:       Mixlab ({cfg.software_id[:12]}…)')
        self.stdout.write(f'Prefijo:        {cfg.prefix}')
        self.stdout.write(f'Resolución:     {cfg.resolution_number}')
        self.stdout.write(f'Vigencia:       {cfg.resolution_from} → {cfg.resolution_to}')
        self.stdout.write(f'Rango:          {cfg.range_from} – {cfg.range_to}')
        self.stdout.write(f'Clave técnica:  {cfg.technical_key[:12]}…')
        self.stdout.write(f'Certificado:    {"Sí" if cfg.has_certificate else "No"}')
        self.stdout.write(f'Test Set ID:    {cfg.test_set_id or "—"}')
        self.stdout.write(f'WS URL:         {cfg.ws_url}')
        if seq:
            self.stdout.write(f'Consecutivo:    {seq.current} (siguiente: {seq.current + 1})')
        self.stdout.write(f'Facturas cotiz: {fe_count} total, {accepted} aceptadas')
        if batch:
            self.stdout.write('')
            self.stdout.write('=== Último lote habilitación ===')
            self.stdout.write(f'Lote #{batch.pk}: {batch.get_status_display()}')
            self.stdout.write(
                f'  {batch.invoice_count} FE · {batch.credit_note_count} NC · '
                f'{batch.debit_note_count} ND'
            )
        self.stdout.write('')
        self.stdout.write('Evaluación completa: python manage.py dian_habilitacion --evaluate')
