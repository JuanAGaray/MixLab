"""Carga de certificado digital .p12 para firma DIAN."""

from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass

from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

from ..config import get_dian_config
from ..exceptions import DianSigningError


@dataclass
class DianCertificate:
    private_key_pem: bytes
    certificate_pem: bytes
    subject_cn: str


def load_certificate() -> DianCertificate:
    """Carga certificado desde ruta o base64 en settings."""
    cfg = get_dian_config()
    p12_bytes = None

    if cfg.certificate_base64:
        try:
            p12_bytes = base64.b64decode(cfg.certificate_base64)
        except Exception as exc:
            raise DianSigningError(f'Certificado base64 inválido: {exc}') from exc
    elif cfg.certificate_path and os.path.isfile(cfg.certificate_path):
        with open(cfg.certificate_path, 'rb') as fh:
            p12_bytes = fh.read()
    else:
        raise DianSigningError(
            'No hay certificado DIAN configurado. Defina DIAN_CERTIFICATE_PATH o DIAN_CERTIFICATE_BASE64.'
        )

    password = (cfg.certificate_password or '').encode('utf-8') or None
    try:
        private_key, certificate, _additional = pkcs12.load_key_and_certificates(p12_bytes, password)
    except Exception as exc:
        raise DianSigningError(f'No se pudo abrir el certificado .p12: {exc}') from exc

    if private_key is None or certificate is None:
        raise DianSigningError('El archivo .p12 no contiene clave privada o certificado.')

    private_key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    certificate_pem = certificate.public_bytes(Encoding.PEM)
    subject = certificate.subject.rfc4514_string()
    return DianCertificate(
        private_key_pem=private_key_pem,
        certificate_pem=certificate_pem,
        subject_cn=subject,
    )


def write_temp_p12() -> str:
    """Escribe certificado temporal para herramientas que requieren archivo."""
    cfg = get_dian_config()
    if cfg.certificate_path and os.path.isfile(cfg.certificate_path):
        return cfg.certificate_path
    if not cfg.certificate_base64:
        raise DianSigningError('Certificado no disponible.')
    data = base64.b64decode(cfg.certificate_base64)
    fd, path = tempfile.mkstemp(prefix='dian_cert_', suffix='.p12')
    with os.fdopen(fd, 'wb') as fh:
        fh.write(data)
    return path
