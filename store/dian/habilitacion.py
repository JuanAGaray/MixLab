"""Requisitos y evaluación del set de habilitación DIAN (SETP)."""

from __future__ import annotations

from dataclasses import dataclass

from store.models import SiteSettings

from .config import get_dian_config
from .models import DianHabilitacionBatch, DianHabilitacionDocument


@dataclass
class HabilitacionCheck:
    label: str
    ok: bool
    detail: str = ''
    required: bool = True


def evaluate_habilitacion() -> list[HabilitacionCheck]:
    """Evalúa configuración y progreso frente a los 50 documentos DIAN."""
    cfg = get_dian_config()
    site = SiteSettings.load()
    batch = DianHabilitacionBatch.objects.order_by('-created_at').first()

    inv_gen = 0
    cn_gen = 0
    dn_gen = 0
    inv_signed = 0
    if batch:
        docs = batch.documents.all()
        inv_gen = docs.filter(doc_type='invoice').count()
        cn_gen = docs.filter(doc_type='credit_note').count()
        dn_gen = docs.filter(doc_type='debit_note').count()
        inv_signed = docs.exclude(xml_signed='').exclude(xml_signed=None).count()

    resolution = (site.dian_invoice_resolution or '').strip()
    checks = [
        HabilitacionCheck(
            'Ambiente habilitación',
            cfg.is_habilitacion,
            cfg.environment,
        ),
        HabilitacionCheck(
            'Software ID (Mixlab)',
            bool(cfg.software_id) and cfg.software_id != 'TU_ID_DEL_SOFTWARE',
            cfg.software_id[:20] + '…' if cfg.software_id else 'Falta',
        ),
        HabilitacionCheck(
            'PIN del software',
            bool(cfg.software_pin) and cfg.software_pin != 'TU_PIN',
            'Configurado' if cfg.software_pin else 'Falta DIAN_SOFTWARE_PIN',
        ),
        HabilitacionCheck(
            'Clave técnica',
            bool(cfg.technical_key),
            cfg.technical_key[:12] + '…' if cfg.technical_key else 'Falta',
        ),
        HabilitacionCheck(
            'Resolución 18760000001',
            resolution == cfg.resolution_number or resolution == '18760000001',
            resolution or 'Configure en Configuración del sitio',
        ),
        HabilitacionCheck(
            'Prefijo SETP',
            cfg.prefix == 'SETP',
            cfg.prefix,
        ),
        HabilitacionCheck(
            'Rango 990000000 – 995000000',
            cfg.range_from == 990000000 and cfg.range_to == 995000000,
            f'{cfg.range_from} - {cfg.range_to}',
        ),
        HabilitacionCheck(
            'Vigencia resolución',
            bool(cfg.resolution_from and cfg.resolution_to),
            f'{cfg.resolution_from} a {cfg.resolution_to}',
        ),
        HabilitacionCheck(
            'Certificado firma .p12',
            cfg.has_certificate,
            'DIAN_CERTIFICATE_PATH o BASE64' if not cfg.has_certificate else 'OK',
        ),
        HabilitacionCheck(
            'Test Set ID (portal DIAN)',
            bool(cfg.test_set_id),
            cfg.test_set_id or 'Copie DIAN_TEST_SET_ID del portal',
        ),
        HabilitacionCheck(
            f'Facturas electrónicas ({cfg.hab_invoices})',
            inv_gen >= cfg.hab_invoices,
            f'{inv_gen}/{cfg.hab_invoices} generadas',
        ),
        HabilitacionCheck(
            f'Notas crédito ({cfg.hab_credit_notes})',
            cn_gen >= cfg.hab_credit_notes,
            f'{cn_gen}/{cfg.hab_credit_notes} generadas',
        ),
        HabilitacionCheck(
            f'Notas débito ({cfg.hab_debit_notes})',
            dn_gen >= cfg.hab_debit_notes,
            f'{dn_gen}/{cfg.hab_debit_notes} generadas',
        ),
        HabilitacionCheck(
            f'Total documentos ({cfg.hab_total_documents})',
            (inv_gen + cn_gen + dn_gen) >= cfg.hab_total_documents,
            f'{inv_gen + cn_gen + dn_gen}/{cfg.hab_total_documents}',
        ),
        HabilitacionCheck(
            'ZIP set de pruebas',
            bool(batch and batch.zip_file),
            batch.zip_file.name if batch and batch.zip_file else 'Ejecute: dian_habilitacion --generate',
            required=False,
        ),
        HabilitacionCheck(
            'Enviado a DIAN (SendTestSetAsync)',
            bool(batch and batch.status in ('submitted', 'accepted')),
            batch.get_status_display() if batch else 'Pendiente',
            required=False,
        ),
    ]
    return checks


def habilitacion_summary() -> dict:
    checks = evaluate_habilitacion()
    required = [c for c in checks if c.required]
    return {
        'checks': checks,
        'ready_to_generate': all(c.ok for c in required[:10]),  # config checks
        'ready_to_submit': all(c.ok for c in checks[:13]) and checks[13].ok,  # all docs + zip
        'passed': sum(1 for c in checks if c.ok),
        'total': len(checks),
    }
