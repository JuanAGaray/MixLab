"""Construcción de UBL 2.1 Invoice para DIAN."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from lxml import etree

from ..config import DianConfig
from ..cufe import compute_cufe, format_dian_amount
from .namespaces import (
    CUSTOMIZATION_ID,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_MUNICIPALITY_CODE,
    DEFAULT_UNIT_CODE,
    DOC_TYPE_CC,
    DOC_TYPE_NIT,
    INVOICE_TYPE_CODE,
    IVA_TAX_SCHEME_ID,
    IVA_TAX_SCHEME_NAME,
    NSMAP,
    PROFILE_ID,
    CURRENCY,
)


IVA_RATE = Decimal('0.19')


def _q(value) -> str:
    return format_dian_amount(value)


def _sub(parent, tag: str, text=None, **attrs):
    el = etree.SubElement(parent, tag, **attrs)
    if text is not None:
        el.text = str(text)
    return el


def parse_nit(raw: str) -> tuple[str, str]:
    """Separa NIT y dígito de verificación."""
    value = (raw or '').strip().replace('.', '').replace(' ', '')
    if '-' in value:
        parts = value.split('-', 1)
        return parts[0], parts[1]
    if len(value) > 1 and value[-1].isdigit():
        return value[:-1], value[-1]
    return value, '0'


def client_document_type(quotation) -> str:
    if getattr(quotation, 'is_empresa_client', False):
        return DOC_TYPE_NIT
    return DOC_TYPE_CC


def client_document_number(quotation) -> str:
    doc = (quotation.display_client_document or quotation.client_document or '').strip()
    doc = re.sub(r'[^\d]', '', doc)
    if getattr(quotation, 'is_empresa_client', False):
        nit, _dv = parse_nit(quotation.display_client_document or quotation.client_document or doc)
        return re.sub(r'[^\d]', '', nit)
    return doc or '222222222222'


@dataclass
class InvoiceLineData:
    line_id: int
    description: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    line_extension: Decimal
    tax_amount: Decimal
    taxable_amount: Decimal


@dataclass
class InvoiceBuildResult:
    xml_bytes: bytes
    cufe: str
    issue_datetime: datetime
    taxable_amount: Decimal
    iva_amount: Decimal
    total_amount: Decimal
    invoice_number: str
    lines: list[InvoiceLineData]


def split_iva_included(amount: Decimal) -> tuple[Decimal, Decimal]:
    base = (amount / (Decimal('1.00') + IVA_RATE)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    iva = (amount - base).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return base, iva


def build_invoice_lines(quotation) -> list[InvoiceLineData]:
    lines = []
    items = quotation.items.select_related('product').all()
    for idx, item in enumerate(items, start=1):
        qty = Decimal(str(item.quantity or 1))
        unit = Decimal(str(item.unit_price or 0))
        subtotal = Decimal(str(item.subtotal or (unit * qty)))
        base, iva = split_iva_included(subtotal)
        name = item.display_name if hasattr(item, 'display_name') else str(item)
        lines.append(
            InvoiceLineData(
                line_id=idx,
                description=name[:300],
                quantity=qty,
                unit_code=DEFAULT_UNIT_CODE,
                unit_price=base / qty if qty else base,
                line_extension=base,
                tax_amount=iva,
                taxable_amount=base,
            )
        )
    return lines


def build_ubl_invoice_xml(
    *,
    quotation,
    site_settings,
    config: DianConfig,
    invoice_number: str,
    issue_datetime: datetime | None = None,
) -> InvoiceBuildResult:
    """Genera XML UBL 2.1 con extensiones DIAN (sin firma)."""
    if issue_datetime is None:
        issue_datetime = datetime.now()

    supplier_nit, supplier_dv = parse_nit(site_settings.company_nit or '')
    customer_doc_type = client_document_type(quotation)
    customer_doc = client_document_number(quotation)

    lines = build_invoice_lines(quotation)
    taxable_amount = sum((ln.taxable_amount for ln in lines), Decimal('0.00'))
    iva_amount = sum((ln.tax_amount for ln in lines), Decimal('0.00'))
    total_amount = taxable_amount + iva_amount

    cufe = compute_cufe(
        invoice_number=invoice_number,
        issue_datetime=issue_datetime,
        taxable_amount=taxable_amount,
        iva_amount=iva_amount,
        total_amount=total_amount,
        supplier_nit=supplier_nit,
        customer_document=customer_doc,
        technical_key=config.technical_key,
        environment_type=config.environment_type_code,
    )

    root = etree.Element('Invoice', nsmap=NSMAP)

    # --- UBLExtensions / DianExtensions ---
    ext_container = _sub(root, '{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtensions')
    ext1 = _sub(ext_container, '{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtension')
    ext_content1 = _sub(ext1, '{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}ExtensionContent')
    dian_ext = _sub(ext_content1, '{dian:gov:co:facturaelectronica:Structures-2-1}DianExtensions')

    inv_control = _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}InvoiceControl')
    _sub(inv_control, '{dian:gov:co:facturaelectronica:Structures-2-1}InvoiceAuthorization', site_settings.dian_invoice_resolution or '18760000001')
    auth_period = _sub(inv_control, '{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizationPeriod')
    _sub(auth_period, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}StartDate', issue_datetime.strftime('%Y-%m-%d'))
    _sub(auth_period, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}EndDate', '2030-12-31')
    auth_inv = _sub(inv_control, '{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizedInvoices')
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}Prefix', config.prefix)
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}From', str(config.range_from))
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}To', str(config.range_to))

    inv_source = _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}InvoiceSource')
    id_country = _sub(inv_source, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}IdentificationCode', DEFAULT_COUNTRY_CODE)
    id_country.set('listAgencyID', '6')
    id_country.set('listAgencyName', 'United Nations Economic Commission for Europe')
    id_country.set('listSchemeURI', 'urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1')

    sw_provider = _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}SoftwareProvider')
    _sub(sw_provider, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ProviderID', supplier_nit, schemeID=supplier_dv, schemeName='31', schemeAgencyID='195', schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
    _sub(sw_provider, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}SoftwareID', config.software_id, schemeAgencyID='195', schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')

    _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}SoftwareSecurityCode', _software_security_code(config, invoice_number, issue_datetime))
    _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizationProvider')
    auth_prov = dian_ext.find('{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizationProvider')
    if auth_prov is not None:
        _sub(auth_prov, '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}AuthorizationProviderID', '800197268', schemeID='4', schemeName='31', schemeAgencyID='195', schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
    _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}QRCode', cufe)

    # Placeholder para firma
    ext2 = _sub(ext_container, '{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtension')
    _sub(ext2, '{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}ExtensionContent')

    cbc = '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}'
    cac = '{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}'

    _sub(root, f'{cbc}UBLVersionID', 'UBL 2.1')
    _sub(root, f'{cbc}CustomizationID', CUSTOMIZATION_ID)
    _sub(root, f'{cbc}ProfileID', PROFILE_ID)
    _sub(root, f'{cbc}ProfileExecutionID', config.profile_execution_id)
    _sub(root, f'{cbc}ID', invoice_number)
    _sub(root, f'{cbc}UUID', cufe, schemeID=config.profile_execution_id, schemeName='CUFE-SHA384')
    _sub(root, f'{cbc}IssueDate', issue_datetime.strftime('%Y-%m-%d'))
    _sub(root, f'{cbc}IssueTime', issue_datetime.strftime('%H:%M:%S-05:00'))
    _sub(root, f'{cbc}InvoiceTypeCode', INVOICE_TYPE_CODE)
    _sub(root, f'{cbc}DocumentCurrencyCode', CURRENCY)
    _sub(root, f'{cbc}LineCountNumeric', str(len(lines)))

    # Nota referencia cotización
    _sub(root, f'{cac}Note', f'Cotización COT-{quotation.id}')

    # Emisor
    supplier_party = _sub(root, f'{cac}AccountingSupplierParty')
    supplier = _sub(supplier_party, f'{cac}Party')
    _add_party_tax_scheme(supplier, site_settings.company_legal_name or 'MIXLAB SAS', supplier_nit, supplier_dv, DOC_TYPE_NIT)
    _add_physical_location(supplier, site_settings.company_address or '', DEFAULT_MUNICIPALITY_CODE, site_settings.company_department or 'Bolívar')
    _add_party_legal_entity(supplier, site_settings.company_legal_name or 'MIXLAB SAS', supplier_nit, supplier_dv, DOC_TYPE_NIT)

    # Adquiriente
    customer_party = _sub(root, f'{cac}AccountingCustomerParty')
    customer = _sub(customer_party, f'{cac}Party')
    cust_name = quotation.display_client_name or quotation.client_name or 'Consumidor final'
    cust_dv = ''
    if customer_doc_type == DOC_TYPE_NIT:
        customer_nit, cust_dv = parse_nit(quotation.display_client_document or '')
        customer_doc = re.sub(r'[^\d]', '', customer_nit)
    _add_party_tax_scheme(customer, cust_name, customer_doc, cust_dv or '0', customer_doc_type)
    _add_physical_location(customer, quotation.display_client_address or quotation.display_client_city or '', DEFAULT_MUNICIPALITY_CODE, quotation.display_client_departamento or '')
    _add_party_legal_entity(customer, cust_name, customer_doc, cust_dv or '0', customer_doc_type)

    # Impuestos totales
    tax_total = _sub(root, f'{cac}TaxTotal')
    _sub(tax_total, f'{cbc}TaxAmount', _q(iva_amount), currencyID=CURRENCY)
    tax_sub = _sub(tax_total, f'{cac}TaxSubtotal')
    _sub(tax_sub, f'{cbc}TaxableAmount', _q(taxable_amount), currencyID=CURRENCY)
    _sub(tax_sub, f'{cbc}TaxAmount', _q(iva_amount), currencyID=CURRENCY)
    tax_cat = _sub(tax_sub, f'{cac}TaxCategory')
    _sub(tax_cat, f'{cbc}Percent', '19.00')
    tax_scheme = _sub(tax_cat, f'{cac}TaxScheme')
    _sub(tax_scheme, f'{cbc}ID', IVA_TAX_SCHEME_ID)
    _sub(tax_scheme, f'{cbc}Name', IVA_TAX_SCHEME_NAME)

    # Totales legales
    legal = _sub(root, f'{cac}LegalMonetaryTotal')
    _sub(legal, f'{cbc}LineExtensionAmount', _q(taxable_amount), currencyID=CURRENCY)
    _sub(legal, f'{cbc}TaxExclusiveAmount', _q(taxable_amount), currencyID=CURRENCY)
    _sub(legal, f'{cbc}TaxInclusiveAmount', _q(total_amount), currencyID=CURRENCY)
    _sub(legal, f'{cbc}PayableAmount', _q(total_amount), currencyID=CURRENCY)

    # Líneas
    for ln in lines:
        inv_line = _sub(root, f'{cac}InvoiceLine')
        _sub(inv_line, f'{cbc}ID', str(ln.line_id))
        _sub(inv_line, f'{cbc}InvoicedQuantity', str(ln.quantity.normalize()), unitCode=ln.unit_code)
        _sub(inv_line, f'{cbc}LineExtensionAmount', _q(ln.line_extension), currencyID=CURRENCY)
        item = _sub(inv_line, f'{cac}Item')
        _sub(item, f'{cbc}Description', ln.description)
        price = _sub(inv_line, f'{cac}Price')
        _sub(price, f'{cbc}PriceAmount', _q(ln.unit_price), currencyID=CURRENCY)
        _sub(price, f'{cbc}BaseQuantity', '1', unitCode=ln.unit_code)
        line_tax = _sub(inv_line, f'{cac}TaxTotal')
        _sub(line_tax, f'{cbc}TaxAmount', _q(ln.tax_amount), currencyID=CURRENCY)
        line_sub = _sub(line_tax, f'{cac}TaxSubtotal')
        _sub(line_sub, f'{cbc}TaxableAmount', _q(ln.taxable_amount), currencyID=CURRENCY)
        _sub(line_sub, f'{cbc}TaxAmount', _q(ln.tax_amount), currencyID=CURRENCY)
        line_cat = _sub(line_sub, f'{cac}TaxCategory')
        _sub(line_cat, f'{cbc}Percent', '19.00')
        line_scheme = _sub(line_cat, f'{cac}TaxScheme')
        _sub(line_scheme, f'{cbc}ID', IVA_TAX_SCHEME_ID)
        _sub(line_scheme, f'{cbc}Name', IVA_TAX_SCHEME_NAME)

    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding='UTF-8',
        pretty_print=True,
    )
    return InvoiceBuildResult(
        xml_bytes=xml_bytes,
        cufe=cufe,
        issue_datetime=issue_datetime,
        taxable_amount=taxable_amount,
        iva_amount=iva_amount,
        total_amount=total_amount,
        invoice_number=invoice_number,
        lines=lines,
    )


def _software_security_code(config: DianConfig, invoice_number: str, issue_datetime: datetime) -> str:
    import hashlib
    chain = f'{config.software_id}{config.software_pin}{invoice_number}'
    return hashlib.sha384(chain.encode('utf-8')).hexdigest()


def _add_party_tax_scheme(party, name: str, doc: str, dv: str, doc_type: str):
    cac = '{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}'
    cbc = '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}'
    tax_scheme = _sub(party, f'{cac}PartyTaxScheme')
    _sub(tax_scheme, f'{cbc}RegistrationName', name)
    _sub(
        tax_scheme,
        f'{cbc}CompanyID',
        doc,
        schemeAgencyID='195',
        schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)',
        schemeID=dv or '0',
        schemeName=str(doc_type),
    )
    ts = _sub(tax_scheme, f'{cac}TaxScheme')
    _sub(ts, f'{cbc}ID', '01')
    _sub(ts, f'{cbc}Name', 'IVA')


def _add_physical_location(party, address: str, municipality_code: str, department: str):
    cac = '{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}'
    cbc = '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}'
    loc = _sub(party, f'{cac}PhysicalLocation')
    addr = _sub(loc, f'{cac}Address')
    _sub(addr, f'{cbc}ID', municipality_code)
    _sub(addr, f'{cbc}CityName', department or 'Cartagena')
    _sub(addr, f'{cbc}CountrySubentity', department or 'Bolívar')
    _sub(addr, f'{cbc}CountrySubentityCode', municipality_code[:2] if len(municipality_code) >= 2 else '13')
    _sub(addr, f'{cbc}Line', address or 'Sin dirección')
    country = _sub(addr, f'{cac}Country')
    _sub(country, f'{cbc}IdentificationCode', DEFAULT_COUNTRY_CODE)


def _add_party_legal_entity(party, name: str, doc: str, dv: str, doc_type: str):
    cac = '{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}'
    cbc = '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}'
    ple = _sub(party, f'{cac}PartyLegalEntity')
    _sub(ple, f'{cbc}RegistrationName', name)
    _sub(
        ple,
        f'{cbc}CompanyID',
        doc,
        schemeAgencyID='195',
        schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)',
        schemeID=dv or '0',
        schemeName=str(doc_type),
    )
