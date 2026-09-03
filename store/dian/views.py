"""Vistas de facturación electrónica DIAN."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from store.models import Quotation

from .exceptions import DianError, DianValidationError
from .models import DianElectronicInvoice
from .pdf import build_dian_invoice_pdf_bytes, ensure_invoice_pdf
from .services.emit import emit_electronic_invoice_from_quotation


def _quotation_paid_enough(quote: Quotation) -> bool:
    return quote.order_status in {
        'pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado',
    }


@staff_member_required
def quotation_dian_invoice(request, quotation_id):
    """Panel / vista de factura electrónica DIAN."""
    quote = get_object_or_404(Quotation, id=quotation_id)
    invoice = DianElectronicInvoice.objects.filter(quotation=quote).first()
    logs = list(invoice.submission_logs.all()[:20]) if invoice else []

    from .config import get_dian_config
    cfg = get_dian_config()

    return render(request, 'store/dian_invoice_detail.html', {
        'quote': quote,
        'invoice': invoice,
        'logs': logs,
        'dian_config': cfg,
        'is_paid': _quotation_paid_enough(quote),
    })


@staff_member_required
@require_POST
def quotation_dian_invoice_emit(request, quotation_id):
    """Emitir o reintentar factura electrónica."""
    quote = get_object_or_404(Quotation, id=quotation_id)
    if not _quotation_paid_enough(quote):
        messages.error(request, 'La cotización debe estar pagada para emitir factura electrónica.')
        return redirect('store:quotation_dian_invoice', quotation_id=quote.id)

    force = request.POST.get('force') == '1'
    submit = request.POST.get('submit_dian', '1') == '1'

    try:
        invoice = emit_electronic_invoice_from_quotation(
            quote,
            emitted_by=request.user,
            submit_to_dian=submit,
            force_new=force,
        )
        ensure_invoice_pdf(invoice)
        if invoice.is_accepted:
            messages.success(request, f'Factura electrónica {invoice.invoice_number} aceptada por DIAN.')
        elif invoice.status == 'signed':
            messages.success(request, f'XML firmado generado ({invoice.invoice_number}). Configure envío a DIAN.')
        elif invoice.status == 'xml_generated':
            messages.info(
                request,
                f'XML generado ({invoice.invoice_number}). Configure certificado DIAN para firmar y enviar.',
            )
        elif invoice.status == 'submitted':
            messages.info(request, f'Enviado a DIAN. Track ID: {invoice.dian_track_id or "—"}')
        elif invoice.status == 'rejected':
            messages.warning(request, f'DIAN rechazó la factura: {invoice.dian_status_message}')
        else:
            messages.warning(request, f'Estado FE: {invoice.get_status_display()}. {invoice.dian_status_message}')
    except DianValidationError as exc:
        messages.error(request, str(exc))
    except DianError as exc:
        messages.error(request, f'Error DIAN: {exc}')

    return redirect('store:quotation_dian_invoice', quotation_id=quote.id)


@staff_member_required
def quotation_dian_invoice_xml(request, quotation_id):
    """Descarga XML firmado o sin firmar."""
    quote = get_object_or_404(Quotation, id=quotation_id)
    invoice = get_object_or_404(DianElectronicInvoice, quotation=quote)
    if invoice.xml_signed:
        try:
            fh = invoice.xml_signed.open('rb')
            return FileResponse(fh, as_attachment=True, filename=f'{invoice.invoice_number}.xml')
        except Exception:
            pass
    if invoice.xml_unsigned:
        return HttpResponse(
            invoice.xml_unsigned,
            content_type='application/xml',
            headers={'Content-Disposition': f'attachment; filename="{invoice.invoice_number}.xml"'},
        )
    raise Http404('XML no disponible')


@staff_member_required
def quotation_dian_invoice_pdf(request, quotation_id):
    """PDF representación gráfica FE."""
    quote = get_object_or_404(Quotation, id=quotation_id)
    invoice = get_object_or_404(DianElectronicInvoice, quotation=quote)
    ensure_invoice_pdf(invoice)
    if invoice.pdf_file:
        try:
            fh = invoice.pdf_file.open('rb')
            download = request.GET.get('download') == '1'
            return FileResponse(
                fh,
                as_attachment=download,
                filename=f'FE-{invoice.invoice_number}.pdf',
            )
        except Exception:
            pass
    data, err = build_dian_invoice_pdf_bytes(invoice)
    if not data:
        return HttpResponse(err or 'No se pudo generar PDF', status=500)
    download = request.GET.get('download') == '1'
    disp = 'attachment' if download else 'inline'
    return HttpResponse(
        data,
        content_type='application/pdf',
        headers={'Content-Disposition': f'{disp}; filename="FE-{invoice.invoice_number}.pdf"'},
    )
