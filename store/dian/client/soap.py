"""Cliente SOAP para webservices DIAN (habilitación y producción)."""

from __future__ import annotations

import base64
import logging
import re
import uuid

import requests

from ..config import get_dian_config
from ..exceptions import DianSubmissionError

logger = logging.getLogger(__name__)


def _extract_tag(xml_text: str, tag: str) -> str:
    pattern = rf'<(?:\w+:)?{tag}[^>]*>([^<]*)</(?:\w+:)?{tag}>'
    match = re.search(pattern, xml_text, re.IGNORECASE | re.DOTALL)
    return (match.group(1) or '').strip() if match else ''


def _soap_envelope(action: str, body_inner: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wcf="http://wcf.dian.colombia">
  <soap:Header/>
  <soap:Body>
    {body_inner}
  </soap:Body>
</soap:Envelope>"""


def send_bill_sync(signed_xml_bytes: bytes, *, file_name: str | None = None) -> dict:
    """
    Envía factura firmada a DIAN vía SendBillSync.
    Retorna dict con success, status_code, message, track_id, raw_response.
    """
    cfg = get_dian_config()
    if not cfg.has_certificate:
        raise DianSubmissionError('Se requiere certificado para enviar a la DIAN.')

    content_b64 = base64.b64encode(signed_xml_bytes).decode('ascii')
    zip_b64 = content_b64  # DIAN acepta XML directo en contentFile para pruebas simples
    fname = file_name or f'fv_{uuid.uuid4().hex[:12]}.xml'

    body = f"""
    <wcf:SendBillSync>
      <wcf:fileName>{fname}</wcf:fileName>
      <wcf:contentFile>{zip_b64}</wcf:contentFile>
    </wcf:SendBillSync>
    """
    envelope = _soap_envelope('SendBillSync', body)
    url = cfg.ws_url

    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'SOAPAction': 'http://wcf.dian.colombia/IWcfDianCustomerServices/SendBillSync',
    }

    try:
        resp = requests.post(
            url,
            data=envelope.encode('utf-8'),
            headers=headers,
            timeout=90,
        )
        raw = resp.text
        logger.info('DIAN SendBillSync status=%s', resp.status_code)

        if resp.status_code >= 400:
            return {
                'success': False,
                'status_code': str(resp.status_code),
                'message': raw[:2000],
                'track_id': '',
                'raw_response': raw,
            }

        is_valid = _extract_tag(raw, 'IsValid').lower() == 'true'
        status_code = _extract_tag(raw, 'StatusCode') or _extract_tag(raw, 'StatusDescription')
        status_message = _extract_tag(raw, 'StatusMessage') or _extract_tag(raw, 'StatusDescription')
        track_id = _extract_tag(raw, 'ZipKey') or _extract_tag(raw, 'TrackId')

        return {
            'success': is_valid or resp.status_code == 200,
            'status_code': status_code,
            'message': status_message or ('Aceptado' if is_valid else 'Respuesta DIAN'),
            'track_id': track_id,
            'raw_response': raw,
        }
    except requests.RequestException as exc:
        raise DianSubmissionError(f'Error de conexión con DIAN: {exc}') from exc


def get_status(track_id: str) -> dict:
    """Consulta estado de documento en DIAN."""
    cfg = get_dian_config()
    body = f"""
    <wcf:GetStatus>
      <wcf:trackId>{track_id}</wcf:trackId>
    </wcf:GetStatus>
    """
    envelope = _soap_envelope('GetStatus', body)
    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'SOAPAction': 'http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatus',
    }
    try:
        resp = requests.post(cfg.ws_url, data=envelope.encode('utf-8'), headers=headers, timeout=60)
        raw = resp.text
        return {
            'success': resp.status_code == 200,
            'status_code': _extract_tag(raw, 'StatusCode'),
            'message': _extract_tag(raw, 'StatusDescription') or raw[:500],
            'raw_response': raw,
        }
    except requests.RequestException as exc:
        raise DianSubmissionError(f'Error consultando estado DIAN: {exc}') from exc


def send_test_set_async(zip_bytes: bytes, *, test_set_id: str, file_name: str = 'habilitacion.zip') -> dict:
    """Envía lote ZIP de habilitación SETP a la DIAN."""
    cfg = get_dian_config()
    content_b64 = base64.b64encode(zip_bytes).decode('ascii')
    body = f"""
    <wcf:SendTestSetAsync>
      <wcf:fileName>{file_name}</wcf:fileName>
      <wcf:contentFile>{content_b64}</wcf:contentFile>
      <wcf:testSetId>{test_set_id}</wcf:testSetId>
    </wcf:SendTestSetAsync>
    """
    envelope = _soap_envelope('SendTestSetAsync', body)
    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'SOAPAction': 'http://wcf.dian.colombia/IWcfDianCustomerServices/SendTestSetAsync',
    }
    try:
        resp = requests.post(cfg.ws_url, data=envelope.encode('utf-8'), headers=headers, timeout=120)
        raw = resp.text
        logger.info('DIAN SendTestSetAsync status=%s', resp.status_code)
        track_id = _extract_tag(raw, 'ZipKey') or _extract_tag(raw, 'TrackId')
        is_valid = _extract_tag(raw, 'IsValid').lower() == 'true'
        return {
            'success': is_valid or (resp.status_code == 200 and bool(track_id)),
            'status_code': _extract_tag(raw, 'StatusCode'),
            'message': _extract_tag(raw, 'StatusMessage') or _extract_tag(raw, 'StatusDescription') or raw[:500],
            'track_id': track_id,
            'raw_response': raw,
        }
    except requests.RequestException as exc:
        raise DianSubmissionError(f'Error enviando set de pruebas: {exc}') from exc
