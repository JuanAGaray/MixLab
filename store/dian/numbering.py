"""Numeración consecutiva DIAN (prefijo SETP en habilitación)."""

from __future__ import annotations

from django.db import transaction

from .config import get_dian_config
from .exceptions import DianValidationError


def _get_sequence_model():
    from .models import DianInvoiceSequence
    return DianInvoiceSequence


def reserve_invoice_number() -> tuple[str, int]:
    """
    Reserva el siguiente consecutivo de forma atómica.
    Retorna (número_completo, consecutivo).
    """
    cfg = get_dian_config()
    Seq = _get_sequence_model()

    with transaction.atomic():
        seq, _ = Seq.objects.select_for_update().get_or_create(
            pk=1,
            defaults={
                'prefix': cfg.prefix,
                'range_from': cfg.range_from,
                'range_to': cfg.range_to,
                'current': cfg.range_from - 1,
            },
        )
        # Sincronizar rango/prefijo desde settings si cambió
        if seq.prefix != cfg.prefix or seq.range_from != cfg.range_from or seq.range_to != cfg.range_to:
            seq.prefix = cfg.prefix
            seq.range_from = cfg.range_from
            seq.range_to = cfg.range_to
            if seq.current < cfg.range_from - 1:
                seq.current = cfg.range_from - 1

        next_num = seq.current + 1
        if next_num > seq.range_to:
            raise DianValidationError(
                f'Se agotó el rango de numeración DIAN ({seq.prefix}{seq.range_from}–{seq.prefix}{seq.range_to}).'
            )
        if next_num < seq.range_from:
            next_num = seq.range_from

        seq.current = next_num
        seq.save(update_fields=['prefix', 'range_from', 'range_to', 'current', 'updated_at'])

    full_number = f'{cfg.prefix}{next_num}'
    return full_number, next_num
