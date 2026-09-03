"""Firma XAdES-EPES del XML UBL para DIAN."""

from __future__ import annotations

import logging

from lxml import etree

from ..exceptions import DianSigningError
from .certificate import load_certificate

logger = logging.getLogger(__name__)


def sign_invoice_xml(xml_bytes: bytes) -> bytes:
    """
    Firma el documento Invoice con XAdES enveloped.
    Requiere certificado .p12 configurado.
    """
    try:
        from signxml import XMLSigner, methods
    except ImportError as exc:
        raise DianSigningError('La librería signxml no está instalada.') from exc

    cert = load_certificate()
    root = etree.fromstring(xml_bytes)

    signer = XMLSigner(
        method=methods.enveloped,
        signature_algorithm='rsa-sha256',
        digest_algorithm='sha256',
        c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315',
    )

    signed_root = signer.sign(
        root,
        key=cert.private_key_pem,
        cert=cert.certificate_pem,
        reference_uri='',
    )

    # Insertar firma en el segundo UBLExtension (ExtensionContent vacío)
    ns_ext = 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    ns_ds = 'http://www.w3.org/2000/09/xmldsig#'
    extensions = signed_root.find(f'{{{ns_ext}}}UBLExtensions')
    if extensions is not None and len(extensions) >= 2:
        ext_content = extensions[1].find(f'{{{ns_ext}}}ExtensionContent')
        signature = signed_root.find(f'.//{{{ns_ds}}}Signature')
        if ext_content is not None and signature is not None:
            # Mover Signature dentro de ExtensionContent
            if signature.getparent() is not signed_root:
                signature.getparent().remove(signature)
            ext_content.append(signature)

    return etree.tostring(
        signed_root,
        xml_declaration=True,
        encoding='UTF-8',
        pretty_print=True,
    )
