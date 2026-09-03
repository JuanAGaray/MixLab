"""Servicio principal: emitir factura electrónica desde cotización."""

from __future__ import annotations

import logging
from datetime import datetime

from django.core.files.base import ContentFile
from django.db import transaction

from store.models import SiteSettings

from ..client.soap import get_status, send_bill_sync
from ..config import get_dian_config
from ..cufe import build_qr_url
from ..exceptions import DianError, DianValidationError
from ..models import DianElectronicInvoice, DianSubmissionLog
from ..numbering import reserve_invoice_number
from ..signing.xades import sign_invoice_xml
from ..ubl.builder import build_ubl_invoice_xml

logger = logging.getLogger(__name__)


def _validate_quotation_for_fe(quotation) -> None:
    if not quotation.items.exists():
        raise DianValidationError('La cotización no tiene ítems.')
    if not (quotation.display_client_name or quotation.client_name):
        raise DianValidationError('Falta el nombre del cliente.')
    if not (quotation.display_client_document or quotation.client_document):
        raise DianValidationError('Falta el documento del cliente (cédula/NIT).')
    email = (quotation.display_client_email or quotation.client_email or '').strip()
    if not email:
        raise DianValidationError('Falta el correo electrónico del cliente (obligatorio para FE).')
    site = SiteSettings.load()
    if not (site.company_nit or '').strip():
        raise DianValidationError('Configure el NIT de la empresa en Configuración del sitio.')
    if not (site.company_legal_name or '').strip():
        raise DianValidationError('Configure la razón social en Configuración del sitio.')


def emit_electronic_invoice_from_quotation(
    quotation,
    *,
    emitted_by=None,
    submit_to_dian: bool = True,
    force_new: bool = False,
) -> DianElectronicInvoice:
    """
    Genera XML UBL, CUFE, firma (si hay certificado) y opcionalmente envía a DIAN.
    Idempotente: si ya existe FE aceptada, la retorna salvo force_new=True.
    """
    existing = getattr(quotation, 'dian_invoice', None)
    if existing and existing.is_accepted and not force_new:
        return existing
    if existing and not force_new and existing.status not in ('error', 'rejected'):
        return existing

    _validate_quotation_for_fe(quotation)
    quotation.sync_client_snapshot_from_profile(save=True)

    cfg = get_dian_config()
    site = SiteSettings.load()

    with transaction.atomic():
        if existing and force_new:
            existing.delete()
            existing = None

        if existing:
            invoice = existing
            invoice_number = invoice.invoice_number
            consecutive = invoice.consecutive
        else:
            invoice_number, consecutive = reserve_invoice_number()
            issue_dt = datetime.now()
            invoice = DianElectronicInvoice(
                quotation=quotation,
                prefix=cfg.prefix,
                consecutive=consecutive,
                invoice_number=invoice_number,
                environment=cfg.environment,
                issue_date=issue_dt.date(),
                issue_time=issue_dt.time().replace(microsecond=0),
                software_id=cfg.software_id,
                technical_key=cfg.technical_key,
                emitted_by=emitted_by,
            )

        build_result = build_ubl_invoice_xml(
            quotation=quotation,
            site_settings=site,
            config=cfg,
            invoice_number=invoice_number,
            issue_datetime=datetime.combine(invoice.issue_date, invoice.issue_time),
        )

        invoice.taxable_amount = build_result.taxable_amount
        invoice.iva_amount = build_result.iva_amount
        invoice.total_amount = build_result.total_amount
        invoice.cufe = build_result.cufe
        invoice.qr_url = build_qr_url(build_result.cufe, cfg.qr_base_url)
        invoice.xml_unsigned = build_result.xml_bytes.decode('utf-8')
        invoice.status = 'xml_generated'
        invoice.save()

    signed_bytes = build_result.xml_bytes
    if cfg.has_certificate:
        try:
            signed_bytes = sign_invoice_xml(build_result.xml_bytes)
            invoice.xml_signed.save(
                f'{invoice_number}.xml',
                ContentFile(signed_bytes),
                save=False,
            )
            invoice.status = 'signed'
            invoice.save(update_fields=['xml_signed', 'status', 'updated_at'])
        except DianError as exc:
            logger.warning('No se pudo firmar FE %s: %s', invoice_number, exc)
            invoice.dian_status_message = str(exc)
            invoice.status = 'error'
            invoice.save(update_fields=['dian_status_message', 'status', 'updated_at'])
            return invoice
    else:
        logger.info('FE %s generada sin firma (certificado no configurado).', invoice_number)

    if submit_to_dian and cfg.has_certificate and invoice.status == 'signed':
        _submit_to_dian(invoice, signed_bytes)

    return invoice


def _submit_to_dian(invoice: DianElectronicInvoice, signed_bytes: bytes) -> None:
    cfg = get_dian_config()
    try:
        result = send_bill_sync(signed_bytes, file_name=f'{invoice.invoice_number}.xml')
    except DianError as exc:
        invoice.status = 'error'
        invoice.dian_status_message = str(exc)
        invoice.save(update_fields=['status', 'dian_status_message', 'updated_at'])
        DianSubmissionLog.objects.create(
            invoice=invoice,
            action='SendBillSync',
            request_summary=f'FE {invoice.invoice_number}',
            response_summary=str(exc),
            success=False,
        )
        return

    invoice.status = 'submitted'
    invoice.dian_track_id = result.get('track_id', '')
    invoice.dian_status_code = result.get('status_code', '')
    invoice.dian_status_message = result.get('message', '')
    invoice.dian_response_raw = result.get('raw_response', '')[:10000]
    if result.get('success'):
        invoice.status = 'accepted'
    else:
        invoice.status = 'rejected' if result.get('status_code') else 'submitted'
    invoice.save()

    DianSubmissionLog.objects.create(
        invoice=invoice,
        action='SendBillSync',
        request_summary=f'FE {invoice.invoice_number}',
        response_summary=f"{result.get('status_code')}: {result.get('message', '')[:500]}",
        success=bool(result.get('success')),
    )

    if invoice.dian_track_id and invoice.status == 'submitted':
        try:
            status_result = get_status(invoice.dian_track_id)
            DianSubmissionLog.objects.create(
                invoice=invoice,
                action='GetStatus',
                request_summary=invoice.dian_track_id,
                response_summary=status_result.get('message', '')[:500],
                success=status_result.get('success', False),
            )
            if status_result.get('success'):
                invoice.dian_status_code = status_result.get('status_code', invoice.dian_status_code)
                invoice.dian_status_message = status_result.get('message', invoice.dian_status_message)
                if 'acept' in (status_result.get('message') or '').lower():
                    invoice.status = 'accepted'
                invoice.save(update_fields=['dian_status_code', 'dian_status_message', 'status', 'updated_at'])
        except DianError:
            pass


def maybe_auto_emit_on_payment(quotation, *, emitted_by=None) -> DianElectronicInvoice | None:
    """Hook post-pago: emite FE si DIAN_AUTO_EMIT_ON_PAYMENT está activo."""
    cfg = get_dian_config()
    if not cfg.auto_emit_on_payment:
        return None
    if hasattr(quotation, 'dian_invoice'):
        return quotation.dian_invoice
    try:
        return emit_electronic_invoice_from_quotation(
            quotation,
            emitted_by=emitted_by,
            submit_to_dian=cfg.has_certificate,
        )
    except DianValidationError as exc:
        logger.warning('Auto-emisión FE cotización %s: %s', quotation.id, exc)
        return None
