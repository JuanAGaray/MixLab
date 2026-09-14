"""Contacto WhatsApp: número de celular o usuario (@usuario)."""

from __future__ import annotations

import re
from urllib.parse import quote

_USERNAME_RE = re.compile(r'^[a-z][a-z0-9._]{2,34}$')


def is_wa_username(raw: str) -> bool:
    value = (raw or '').strip()
    if not value:
        return False
    if '@' in value and not value.startswith('@'):
        return False
    candidate = value[1:] if value.startswith('@') else value
    candidate = candidate.strip().lower()
    return bool(_USERNAME_RE.match(candidate)) and any(ch.isalpha() for ch in candidate)


def normalize_wa_phone(phone: str) -> str:
    """Teléfono a dígitos con indicativo Colombia (57) si aplica."""
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if not digits:
        return ''
    if digits.startswith('57') and len(digits) >= 12:
        return digits
    if len(digits) == 10:
        return f'57{digits}'
    if digits.startswith('0') and len(digits) == 11:
        return f'57{digits.lstrip("0")}'
    return digits


def normalize_wa_contact(raw: str) -> str:
    """
    Devuelve el destino para wa.me / n8n.
    - Usuario: mixlab.eventos (sin @)
    - Celular: 573001234567
    - JID / grupo (57300@s.whatsapp.net, ...@g.us): se conserva
    """
    value = (raw or '').strip()
    if not value:
        return ''
    if '@' in value and not value.startswith('@'):
        return value
    if is_wa_username(value):
        candidate = value[1:] if value.startswith('@') else value
        return candidate.strip().lower()
    return normalize_wa_phone(value)


def wa_me_url(contact: str, message: str = '') -> str:
    """URL wa.me para celular o usuario, con mensaje opcional."""
    target = normalize_wa_contact(contact)
    if not target:
        return ''
    url = f'https://wa.me/{target}'
    text = (message or '').strip()
    if text:
        url += f'?text={quote(text)}'
    return url


def apply_phone_indicative(value: str, indicative: str = '+57') -> str:
    """Prefija +57 solo si es un celular, no un usuario de WhatsApp."""
    value = (value or '').strip()
    if not value or is_wa_username(value):
        return value.lstrip('@').strip().lower() if is_wa_username(value) else value
    if value.startswith('+'):
        return value
    return f'{indicative} {value}'
