"""Namespaces UBL 2.1 / DIAN."""

NSMAP = {
    None: 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
    'xades': 'http://uri.etsi.org/01903/v1.3.2#',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}

INVOICE_TYPE_CODE = '01'
CUSTOMIZATION_ID = '10'
PROFILE_ID = 'DIAN 2.1: Factura Electrónica de Venta'
CURRENCY = 'COP'
IVA_TAX_SCHEME_ID = '01'
IVA_TAX_SCHEME_NAME = 'IVA'

# Tipos de documento DIAN
DOC_TYPE_NIT = '31'
DOC_TYPE_CC = '13'
DOC_TYPE_CE = '22'
DOC_TYPE_PASSPORT = '41'

# Códigos municipio por defecto (Cartagena / Bolívar)
DEFAULT_MUNICIPALITY_CODE = '13001'
DEFAULT_COUNTRY_CODE = 'CO'
DEFAULT_UNIT_CODE = '94'  # unidad
