"""XML UBL de prueba para habilitación SETP (sin cotización)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from lxml import etree

from ..config import DianConfig
from ..cufe import compute_cufe, format_dian_amount
from .builder import (
    _add_party_legal_entity,
    _add_party_tax_scheme,
    _add_physical_location,
    _sub,
    parse_nit,
    split_iva_included,
)
from .namespaces import (
    CURRENCY,
    CUSTOMIZATION_ID,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_MUNICIPALITY_CODE,
    DEFAULT_UNIT_CODE,
    DOC_TYPE_CC,
    DOC_TYPE_NIT,
    IVA_TAX_SCHEME_ID,
    IVA_TAX_SCHEME_NAME,
)

IVA_RATE = Decimal('0.19')
CUSTOMER_DOC = '900123456'
CUSTOMER_NAME = 'Cliente Habilitación DIAN'


def _q(value) -> str:
    return format_dian_amount(value)


def _software_security_code(config: DianConfig, document_number: str) -> str:
    chain = f'{config.software_id}{config.software_pin}{document_number}'
    return hashlib.sha384(chain.encode('utf-8')).hexdigest()


def _dian_extensions(
    root_tag: str,
    *,
    config: DianConfig,
    site_settings,
    document_number: str,
    issue_datetime: datetime,
    unique_code: str,
    resolution_from: str,
    resolution_to: str,
):
    if root_tag == 'Invoice':
        nsmap = {
            None: 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
        }
    elif root_tag == 'CreditNote':
        nsmap = {
            None: 'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
        }
    else:
        nsmap = {
            None: 'urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
        }
    return nsmap


@dataclass
class TestDocumentResult:
    xml_bytes: bytes
    unique_code: str
    document_number: str
    taxable_amount: Decimal
    iva_amount: Decimal
    total_amount: Decimal
    issue_datetime: datetime


def _build_base_document(
    *,
    root_tag: str,
    profile_id: str,
    customization_id: str,
    type_code: str,
    type_code_tag: str,
    line_tag: str,
    quantity_tag: str,
    config: DianConfig,
    site_settings,
    document_number: str,
    issue_datetime: datetime,
    gross_amount: Decimal,
    reference_number: str = '',
    reference_cufe: str = '',
    reference_date: str = '',
) -> TestDocumentResult:
    supplier_nit, supplier_dv = parse_nit(site_settings.company_nit or '902031074-1')
    base, iva = split_iva_included(gross_amount)
    total = base + iva

    unique_code = compute_cufe(
        invoice_number=document_number,
        issue_datetime=issue_datetime,
        taxable_amount=base,
        iva_amount=iva,
        total_amount=total,
        supplier_nit=supplier_nit,
        customer_document=CUSTOMER_DOC,
        technical_key=config.technical_key,
        environment_type=config.environment_type_code,
    )

    nsmap = _dian_extensions(
        root_tag,
        config=config,
        site_settings=site_settings,
        document_number=document_number,
        issue_datetime=issue_datetime,
        unique_code=unique_code,
        resolution_from=config.resolution_from,
        resolution_to=config.resolution_to,
    )
    root = etree.Element(root_tag, nsmap=nsmap)

    ext_ns = 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    ext_container = _sub(root, f'{{{ext_ns}}}UBLExtensions')
    ext1 = _sub(ext_container, f'{{{ext_ns}}}UBLExtension')
    ext_content1 = _sub(ext1, f'{{{ext_ns}}}ExtensionContent')
    dian_ext = _sub(ext_content1, '{dian:gov:co:facturaelectronica:Structures-2-1}DianExtensions')

    inv_control = _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}InvoiceControl')
    _sub(
        inv_control,
        '{dian:gov:co:facturaelectronica:Structures-2-1}InvoiceAuthorization',
        site_settings.dian_invoice_resolution or config.resolution_number,
    )
    auth_period = _sub(inv_control, '{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizationPeriod')
    cbc = '{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}'
    _sub(auth_period, f'{cbc}StartDate', config.resolution_from)
    _sub(auth_period, f'{cbc}EndDate', config.resolution_to)
    auth_inv = _sub(inv_control, '{dian:gov:co:facturaelectronica:Structures-2-1}AuthorizedInvoices')
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}Prefix', config.prefix)
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}From', str(config.range_from))
    _sub(auth_inv, '{dian:gov:co:facturaelectronica:Structures-2-1}To', str(config.range_to))

    sw_provider = _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}SoftwareProvider')
    _sub(sw_provider, f'{cbc}ProviderID', supplier_nit, schemeID=supplier_dv, schemeName='31', schemeAgencyID='195', schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
    _sub(sw_provider, f'{cbc}SoftwareID', config.software_id, schemeAgencyID='195', schemeAgencyName='CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
    _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}SoftwareSecurityCode', _software_security_code(config, document_number))
    _sub(dian_ext, '{dian:gov:co:facturaelectronica:Structures-2-1}QRCode', unique_code)

    ext2 = _sub(ext_container, f'{{{ext_ns}}}UBLExtension')
    _sub(ext2, f'{{{ext_ns}}}ExtensionContent')

    cac = '{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}'
    scheme_name = 'CUFE-SHA384' if root_tag == 'Invoice' else 'CUDE-SHA384'

    _sub(root, f'{cbc}UBLVersionID', 'UBL 2.1')
    _sub(root, f'{cbc}CustomizationID', customization_id)
    _sub(root, f'{cbc}ProfileID', profile_id)
    _sub(root, f'{cbc}ProfileExecutionID', config.profile_execution_id)
    _sub(root, f'{cbc}ID', document_number)
    _sub(root, f'{cbc}UUID', unique_code, schemeID=config.profile_execution_id, schemeName=scheme_name)
    _sub(root, f'{cbc}IssueDate', issue_datetime.strftime('%Y-%m-%d'))
    _sub(root, f'{cbc}IssueTime', issue_datetime.strftime('%H:%M:%S-05:00'))
    _sub(root, f'{cbc}{type_code_tag}', type_code)
    _sub(root, f'{cbc}DocumentCurrencyCode', CURRENCY)
    _sub(root, f'{cbc}LineCountNumeric', '1')

    if reference_number:
        billing_ref = _sub(root, f'{cac}BillingReference')
        inv_doc_ref = _sub(billing_ref, f'{cac}InvoiceDocumentReference')
        _sub(inv_doc_ref, f'{cbc}ID', reference_number)
        _sub(inv_doc_ref, f'{cbc}UUID', reference_cufe, schemeName=scheme_name)
        if reference_date:
            _sub(inv_doc_ref, f'{cbc}IssueDate', reference_date)

    supplier_party = _sub(root, f'{cac}AccountingSupplierParty')
    supplier = _sub(supplier_party, f'{cac}Party')
    _add_party_tax_scheme(supplier, site_settings.company_legal_name or 'MIXLAB SAS', supplier_nit, supplier_dv, DOC_TYPE_NIT)
    _add_physical_location(supplier, site_settings.company_address or '', DEFAULT_MUNICIPALITY_CODE, site_settings.company_department or 'Bolívar')
    _add_party_legal_entity(supplier, site_settings.company_legal_name or 'MIXLAB SAS', supplier_nit, supplier_dv, DOC_TYPE_NIT)

    customer_party = _sub(root, f'{cac}AccountingCustomerParty')
    customer = _sub(customer_party, f'{cac}Party')
    _add_party_tax_scheme(customer, CUSTOMER_NAME, CUSTOMER_DOC, '1', DOC_TYPE_NIT)
    _add_physical_location(customer, 'Cartagena', DEFAULT_MUNICIPALITY_CODE, 'Bolívar')
    _add_party_legal_entity(customer, CUSTOMER_NAME, CUSTOMER_DOC, '1', DOC_TYPE_NIT)

    tax_total = _sub(root, f'{cac}TaxTotal')
    _sub(tax_total, f'{cbc}TaxAmount', _q(iva), currencyID=CURRENCY)
    tax_sub = _sub(tax_total, f'{cac}TaxSubtotal')
    _sub(tax_sub, f'{cbc}TaxableAmount', _q(base), currencyID=CURRENCY)
    _sub(tax_sub, f'{cbc}TaxAmount', _q(iva), currencyID=CURRENCY)
    tax_cat = _sub(tax_sub, f'{cac}TaxCategory')
    _sub(tax_cat, f'{cbc}Percent', '19.00')
    tax_scheme = _sub(tax_cat, f'{cac}TaxScheme')
    _sub(tax_scheme, f'{cbc}ID', IVA_TAX_SCHEME_ID)
    _sub(tax_scheme, f'{cbc}Name', IVA_TAX_SCHEME_NAME)

    legal = _sub(root, f'{cac}LegalMonetaryTotal')
    _sub(legal, f'{cbc}LineExtensionAmount', _q(base), currencyID=CURRENCY)
    _sub(legal, f'{cbc}TaxExclusiveAmount', _q(base), currencyID=CURRENCY)
    _sub(legal, f'{cbc}TaxInclusiveAmount', _q(total), currencyID=CURRENCY)
    _sub(legal, f'{cbc}PayableAmount', _q(total), currencyID=CURRENCY)

    doc_line = _sub(root, f'{cac}{line_tag}')
    _sub(doc_line, f'{cbc}ID', '1')
    _sub(doc_line, f'{cbc}{quantity_tag}', '1', unitCode=DEFAULT_UNIT_CODE)
    _sub(doc_line, f'{cbc}LineExtensionAmount', _q(base), currencyID=CURRENCY)
    item = _sub(doc_line, f'{cac}Item')
    desc = f'Documento habilitación {document_number}'
    _sub(item, f'{cbc}Description', desc)
    price = _sub(doc_line, f'{cac}Price')
    _sub(price, f'{cbc}PriceAmount', _q(base), currencyID=CURRENCY)
    _sub(price, f'{cbc}BaseQuantity', '1', unitCode=DEFAULT_UNIT_CODE)

    xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
    return TestDocumentResult(
        xml_bytes=xml_bytes,
        unique_code=unique_code,
        document_number=document_number,
        taxable_amount=base,
        iva_amount=iva,
        total_amount=total,
        issue_datetime=issue_datetime,
    )


def build_habilitacion_invoice(
    *,
    config: DianConfig,
    site_settings,
    document_number: str,
    issue_datetime: datetime | None = None,
    amount: Decimal | None = None,
) -> TestDocumentResult:
    if issue_datetime is None:
        issue_datetime = datetime.now()
    gross = amount or Decimal('119000.00')
    return _build_base_document(
        root_tag='Invoice',
        profile_id='DIAN 2.1: Factura Electrónica de Venta',
        customization_id='10',
        type_code='01',
        type_code_tag='InvoiceTypeCode',
        line_tag='InvoiceLine',
        quantity_tag='InvoicedQuantity',
        config=config,
        site_settings=site_settings,
        document_number=document_number,
        issue_datetime=issue_datetime,
        gross_amount=gross,
    )


def build_habilitacion_credit_note(
    *,
    config: DianConfig,
    site_settings,
    document_number: str,
    reference_number: str,
    reference_cufe: str,
    reference_date: str,
    issue_datetime: datetime | None = None,
    amount: Decimal | None = None,
) -> TestDocumentResult:
    if issue_datetime is None:
        issue_datetime = datetime.now()
    gross = amount or Decimal('59500.00')
    return _build_base_document(
        root_tag='CreditNote',
        profile_id='DIAN 2.1: Nota Crédito de Factura Electrónica de Venta',
        customization_id='20',
        type_code='91',
        type_code_tag='CreditNoteTypeCode',
        line_tag='CreditNoteLine',
        quantity_tag='CreditedQuantity',
        config=config,
        site_settings=site_settings,
        document_number=document_number,
        issue_datetime=issue_datetime,
        gross_amount=gross,
        reference_number=reference_number,
        reference_cufe=reference_cufe,
        reference_date=reference_date,
    )


def build_habilitacion_debit_note(
    *,
    config: DianConfig,
    site_settings,
    document_number: str,
    reference_number: str,
    reference_cufe: str,
    reference_date: str,
    issue_datetime: datetime | None = None,
    amount: Decimal | None = None,
) -> TestDocumentResult:
    if issue_datetime is None:
        issue_datetime = datetime.now()
    gross = amount or Decimal('23800.00')
    return _build_base_document(
        root_tag='DebitNote',
        profile_id='DIAN 2.1: Nota Débito de Factura Electrónica de Venta',
        customization_id='30',
        type_code='92',
        type_code_tag='DebitNoteTypeCode',
        line_tag='DebitNoteLine',
        quantity_tag='DebitedQuantity',
        config=config,
        site_settings=site_settings,
        document_number=document_number,
        issue_datetime=issue_datetime,
        gross_amount=gross,
        reference_number=reference_number,
        reference_cufe=reference_cufe,
        reference_date=reference_date,
    )
