"""Comando: emitir factura electrónica DIAN desde cotización."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from store.dian.exceptions import DianError, DianValidationError
from store.dian.pdf import ensure_invoice_pdf
from store.dian.services.emit import emit_electronic_invoice_from_quotation
from store.models import Quotation


class Command(BaseCommand):
    help = 'Emite factura electrónica DIAN para una cotización pagada.'

    def add_arguments(self, parser):
        parser.add_argument('--quotation', type=int, required=True, help='ID de cotización')
        parser.add_argument('--no-submit', action='store_true', help='Solo generar XML, no enviar a DIAN')
        parser.add_argument('--force', action='store_true', help='Reemitir aunque ya exista FE')

    def handle(self, *args, **options):
        qid = options['quotation']
        try:
            quote = Quotation.objects.get(pk=qid)
        except Quotation.DoesNotExist as exc:
            raise CommandError(f'Cotización {qid} no existe') from exc

        user = get_user_model().objects.filter(is_superuser=True).first()
        try:
            invoice = emit_electronic_invoice_from_quotation(
                quote,
                emitted_by=user,
                submit_to_dian=not options['no_submit'],
                force_new=options['force'],
            )
            ensure_invoice_pdf(invoice)
        except (DianValidationError, DianError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f'FE {invoice.invoice_number} · estado={invoice.status} · CUFE={invoice.cufe[:16]}…'
        ))
