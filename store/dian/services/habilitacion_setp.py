"""Generación del lote SETP (50 documentos) para habilitación DIAN."""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.db import transaction

from store.models import SiteSettings

from ..config import get_dian_config
from ..exceptions import DianError, DianValidationError
from ..models import DianHabilitacionBatch, DianHabilitacionDocument
from ..numbering import reserve_invoice_number
from ..signing.xades import sign_invoice_xml
from ..ubl.test_documents import (
    build_habilitacion_credit_note,
    build_habilitacion_debit_note,
    build_habilitacion_invoice,
)

logger = logging.getLogger(__name__)


def _ensure_site_resolution(site) -> None:
    if not (site.dian_invoice_resolution or '').strip():
        cfg = get_dian_config()
        site.dian_invoice_resolution = cfg.resolution_number
        site.save(update_fields=['dian_invoice_resolution', 'updated_at'])


@transaction.atomic
def generate_habilitacion_batch(*, sign: bool = True) -> DianHabilitacionBatch:
    """Genera 30 FE + 10 NC + 10 ND para el set de habilitación."""
    cfg = get_dian_config()
    site = SiteSettings.load()
    _ensure_site_resolution(site)

    if not cfg.technical_key or not cfg.software_id or not cfg.software_pin:
        raise DianValidationError('Configure DIAN_SOFTWARE_ID, PIN y clave técnica en .env')

    total_needed = cfg.hab_total_documents
    from ..models import DianInvoiceSequence
    seq = DianInvoiceSequence.objects.filter(pk=1).first()
    next_num = (seq.current + 1) if seq else cfg.range_from
    if next_num + total_needed - 1 > cfg.range_to:
        raise DianValidationError(
            f'Se necesitan {total_needed} consecutivos pero el rango SETP no alcanza.'
        )

    batch = DianHabilitacionBatch.objects.create(
        test_set_id=cfg.test_set_id,
        status='draft',
    )

    invoices_meta: list[dict] = []
    base_dt = datetime.now()
    can_sign = sign and cfg.has_certificate

    # --- Facturas (30) ---
    for i in range(cfg.hab_invoices):
        doc_number, consecutive = reserve_invoice_number()
        issue_dt = base_dt + timedelta(seconds=i)
        result = build_habilitacion_invoice(
            config=cfg,
            site_settings=site,
            document_number=doc_number,
            issue_datetime=issue_dt,
            amount=decimal_amount(i),
        )
        signed_bytes = result.xml_bytes
        if can_sign:
            try:
                signed_bytes = sign_invoice_xml(result.xml_bytes)
            except DianError as exc:
                logger.warning('No se firmó %s: %s', doc_number, exc)
                can_sign = False

        doc = DianHabilitacionDocument(
            batch=batch,
            doc_type='invoice',
            document_number=doc_number,
            consecutive=consecutive,
            cufe_cude=result.unique_code,
            xml_unsigned=result.xml_bytes.decode('utf-8'),
        )
        if can_sign:
            doc.xml_signed.save(f'{doc_number}.xml', ContentFile(signed_bytes), save=False)
        doc.save()
        invoices_meta.append({
            'number': doc_number,
            'cufe': result.unique_code,
            'date': issue_dt.strftime('%Y-%m-%d'),
        })

    # --- Notas crédito (10) — referencian facturas 1-10 ---
    for i in range(cfg.hab_credit_notes):
        ref = invoices_meta[i % len(invoices_meta)]
        doc_number, consecutive = reserve_invoice_number()
        issue_dt = base_dt + timedelta(seconds=30 + i)
        result = build_habilitacion_credit_note(
            config=cfg,
            site_settings=site,
            document_number=doc_number,
            reference_number=ref['number'],
            reference_cufe=ref['cufe'],
            reference_date=ref['date'],
            issue_datetime=issue_dt,
        )
        signed_bytes = result.xml_bytes
        if can_sign:
            signed_bytes = sign_invoice_xml(result.xml_bytes)
        doc = DianHabilitacionDocument(
            batch=batch,
            doc_type='credit_note',
            document_number=doc_number,
            consecutive=consecutive,
            cufe_cude=result.unique_code,
            reference_number=ref['number'],
            reference_cufe=ref['cufe'],
            xml_unsigned=result.xml_bytes.decode('utf-8'),
        )
        if can_sign:
            doc.xml_signed.save(f'{doc_number}.xml', ContentFile(signed_bytes), save=False)
        doc.save()

    # --- Notas débito (10) — referencian facturas 11-20 ---
    for i in range(cfg.hab_debit_notes):
        ref = invoices_meta[(10 + i) % len(invoices_meta)]
        doc_number, consecutive = reserve_invoice_number()
        issue_dt = base_dt + timedelta(seconds=40 + i)
        result = build_habilitacion_debit_note(
            config=cfg,
            site_settings=site,
            document_number=doc_number,
            reference_number=ref['number'],
            reference_cufe=ref['cufe'],
            reference_date=ref['date'],
            issue_datetime=issue_dt,
        )
        signed_bytes = result.xml_bytes
        if can_sign:
            signed_bytes = sign_invoice_xml(result.xml_bytes)
        doc = DianHabilitacionDocument(
            batch=batch,
            doc_type='debit_note',
            document_number=doc_number,
            consecutive=consecutive,
            cufe_cude=result.unique_code,
            reference_number=ref['number'],
            reference_cufe=ref['cufe'],
            xml_unsigned=result.xml_bytes.decode('utf-8'),
        )
        if can_sign:
            doc.xml_signed.save(f'{doc_number}.xml', ContentFile(signed_bytes), save=False)
        doc.save()

    batch.invoice_count = cfg.hab_invoices
    batch.credit_note_count = cfg.hab_credit_notes
    batch.debit_note_count = cfg.hab_debit_notes
    batch.status = 'signed' if can_sign else 'generated'
    batch.save()

    _build_batch_zip(batch)
    return batch


def decimal_amount(index: int):
    from decimal import Decimal
    amounts = [119000, 238000, 59500, 178500, 357000]
    return Decimal(str(amounts[index % len(amounts)]))


def _build_batch_zip(batch: DianHabilitacionBatch) -> None:
    """Empaqueta todos los XML del lote en un ZIP para SendTestSetAsync."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for doc in batch.documents.order_by('consecutive'):
            if doc.xml_signed:
                try:
                    data = doc.xml_signed.read()
                except Exception:
                    data = doc.xml_unsigned.encode('utf-8')
            else:
                data = doc.xml_unsigned.encode('utf-8')
            zf.writestr(f'{doc.document_number}.xml', data)
    buffer.seek(0)
    batch.zip_file.save(f'SETP_batch_{batch.pk}.zip', ContentFile(buffer.read()), save=True)
    batch.status = 'zipped'
    batch.save(update_fields=['zip_file', 'status', 'updated_at'])


def submit_habilitacion_batch(batch: DianHabilitacionBatch | None = None) -> dict:
    """Envía el ZIP al webservice SendTestSetAsync de la DIAN."""
    from ..client.soap import send_test_set_async

    cfg = get_dian_config()
    if not cfg.test_set_id:
        raise DianValidationError('Configure DIAN_TEST_SET_ID (ID del set en el portal DIAN).')
    if not batch:
        batch = DianHabilitacionBatch.objects.filter(status='zipped').order_by('-created_at').first()
    if not batch or not batch.zip_file:
        raise DianValidationError('No hay lote ZIP generado. Ejecute dian_habilitacion --generate primero.')

    with batch.zip_file.open('rb') as fh:
        zip_bytes = fh.read()

    result = send_test_set_async(zip_bytes, test_set_id=cfg.test_set_id)
    batch.dian_track_id = result.get('track_id', '')
    batch.dian_response = result.get('raw_response', '')[:10000]
    if result.get('success'):
        batch.status = 'submitted'
    else:
        batch.status = 'rejected'
    batch.save()
    return result
