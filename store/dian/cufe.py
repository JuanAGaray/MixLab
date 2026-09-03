"""Cálculo de CUFE (Código Único de Factura Electrónica) según DIAN."""

from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP


def format_dian_amount(value) -> str:
    """Monto con 2 decimales sin separadores de miles."""
    amount = Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f'{amount:.2f}'


def format_dian_date(dt) -> str:
    """YYYYMMDD en zona horaria del datetime."""
    return dt.strftime('%Y%m%d')


def format_dian_time(dt) -> str:
    """HHMMSS-05:00 (offset Colombia)."""
    return dt.strftime('%H%M%S-05:00')


def compute_cufe(
    *,
    invoice_number: str,
    issue_datetime,
    taxable_amount,
    iva_amount,
    total_amount,
    supplier_nit: str,
    customer_document: str,
    technical_key: str,
    environment_type: str,
    other_tax_code: str = '',
    other_tax_amount=None,
    inc_tax_code: str = '',
    inc_tax_amount=None,
) -> str:
    """
    SHA-384 del encadenamiento DIAN:
    NumFac + FecFac + HorFac + ValFac + CodImp1 + ValImp1 + CodImp2 + ValImp2
    + CodImp3 + ValImp3 + ValTot + NitOFE + NumAdq + ClTec + TipoAmbiente
    """
    cod_imp1 = '01'
    val_imp1 = format_dian_amount(iva_amount)
    cod_imp2 = other_tax_code or ''
    val_imp2 = format_dian_amount(other_tax_amount or 0) if cod_imp2 else ''
    cod_imp3 = inc_tax_code or ''
    val_imp3 = format_dian_amount(inc_tax_amount or 0) if cod_imp3 else ''

    chain = (
        f'{invoice_number}'
        f'{format_dian_date(issue_datetime)}'
        f'{format_dian_time(issue_datetime)}'
        f'{format_dian_amount(taxable_amount)}'
        f'{cod_imp1}'
        f'{val_imp1}'
        f'{cod_imp2}'
        f'{val_imp2}'
        f'{cod_imp3}'
        f'{val_imp3}'
        f'{format_dian_amount(total_amount)}'
        f'{supplier_nit}'
        f'{customer_document}'
        f'{technical_key}'
        f'{environment_type}'
    )
    return hashlib.sha384(chain.encode('utf-8')).hexdigest()


def build_qr_url(cufe: str, qr_base_url: str) -> str:
    base = (qr_base_url or '').rstrip('=')
    if base.endswith('documentkey'):
        return f'{base}={cufe}'
    if base.endswith('documentkey='):
        return f'{base}{cufe}'
    return f'{base}{cufe}'
