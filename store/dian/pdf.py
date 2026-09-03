"""Generación de PDF representación gráfica de factura electrónica."""

from __future__ import annotations

import logging
import os

from django.template.loader import get_template

from store.models import SiteSettings

logger = logging.getLogger(__name__)


def build_dian_invoice_pdf_bytes(invoice) -> tuple[bytes | None, str | None]:
    """Genera PDF de representación gráfica con xhtml2pdf."""
    try:
        from io import BytesIO
        from xhtml2pdf import pisa
    except ImportError:
        return None, 'xhtml2pdf no está instalado'

    quotation = invoice.quotation
    site = SiteSettings.load()
    items = list(quotation.items.select_related('product').all())

    template = get_template('store/dian_invoice_pdf.html')
    html = template.render({
        'invoice': invoice,
        'quote': quotation,
        'items': items,
        'site': site,
        'for_pdf_engine': True,
    })

    result = BytesIO()
    from store.views import _pdf_link_callback
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        return None, f'Error generando PDF: {pdf.err}'
    return result.getvalue(), None


def ensure_invoice_pdf(invoice) -> None:
    """Genera y guarda PDF si no existe."""
    if invoice.pdf_file:
        return
    data, err = build_dian_invoice_pdf_bytes(invoice)
    if not data:
        logger.warning('PDF FE %s: %s', invoice.invoice_number, err)
        return
    from django.core.files.base import ContentFile
    invoice.pdf_file.save(f'{invoice.invoice_number}.pdf', ContentFile(data), save=True)
