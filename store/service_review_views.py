"""Reseña pública de servicio + cupón bono redimible."""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Quotation,
    QuotationItem,
    QuotationServiceReview,
    ServiceBonusCoupon,
    SiteSettings,
)


def _generate_access_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _generate_coupon_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    for _ in range(20):
        code = 'MIX-' + ''.join(secrets.choice(alphabet) for _ in range(6))
        if not ServiceBonusCoupon.objects.filter(code=code).exists():
            return code
    return 'MIX-' + uuid.uuid4().hex[:8].upper()


def _session_key(token) -> str:
    return f'service_review_unlocked_{token}'


def _get_review_by_token(token) -> QuotationServiceReview:
    return get_object_or_404(
        QuotationServiceReview.objects.select_related('quotation', 'bonus_coupon'),
        access_token=token,
    )


def _wa_me_url(phone: str, message: str = '') -> str:
    from .views import _wa_me_url as wa
    return wa(phone, message)


def _notify_whatsapp_n8n(*, message: str, phone: str = '', request=None) -> bool:
    from .views import _notify_whatsapp_n8n as notify
    return notify(message=message, phone=phone, request=request)


def _ensure_review(quote: Quotation) -> QuotationServiceReview:
    review, _ = QuotationServiceReview.objects.get_or_create(quotation=quote)
    return review


@staff_member_required
def quotation_review_manage(request, quotation_id):
    """Staff: generar enlace + código y enviar reseña por WhatsApp."""
    q = get_object_or_404(
        Quotation.objects.select_related('existing_client', 'created_by'),
        id=quotation_id,
    )
    settings_obj = SiteSettings.load()
    review = _ensure_review(q)
    plain_code = (review.access_code or '').strip()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'generate_link':
            code = _generate_access_code()
            days = getattr(settings_obj, 'review_link_days', 30) or 30
            try:
                days = max(1, min(90, int(request.POST.get('expire_days') or days)))
            except (TypeError, ValueError):
                days = 30
            if not review.access_token:
                review.access_token = uuid.uuid4()
            review.access_code = code
            review.access_code_hash = make_password(code)
            review.link_expires_at = timezone.now() + timedelta(days=days)
            review.save(update_fields=[
                'access_token', 'access_code', 'access_code_hash',
                'link_expires_at', 'updated_at',
            ])
            messages.success(request, 'Enlace y código generados. Ya puedes copiarlos o enviarlos al cliente.')
            return redirect('store:quotation_review_manage', quotation_id=q.id)

        if action == 'revoke_link':
            review.access_code = ''
            review.access_code_hash = ''
            review.link_expires_at = timezone.now()
            review.save(update_fields=[
                'access_code', 'access_code_hash', 'link_expires_at', 'updated_at',
            ])
            messages.info(request, 'El enlace quedó deshabilitado. Genera uno nuevo para volver a compartirlo.')
            return redirect('store:quotation_review_manage', quotation_id=q.id)

        if action == 'send_wa':
            plain_code = (review.access_code or '').strip()
            if not review.link_is_active or not plain_code:
                messages.error(request, 'Genera primero un enlace activo con código.')
                return redirect('store:quotation_review_manage', quotation_id=q.id)
            client_link = request.build_absolute_uri(
                reverse('store:service_review_unlock', kwargs={'token': str(review.access_token)})
            )
            share_message = (
                f'Hola {q.display_client_name or ""},\n\n'
                f'Gracias por confiar en MixLab (COT-{q.id}).\n'
                f'Te invitamos a calificar nuestro servicio. Solo toma un minuto:\n\n'
                f'Enlace: {client_link}\n'
                f'Código de verificación (para abrir el formulario): {plain_code}\n\n'
                f'Al completar la reseña recibirás un bono MIX-XXXXXX '
                f'del {settings_obj.review_bonus_percent}% (válido '
                f'{settings_obj.review_bonus_days} días). Ese bono se canjea '
                f'con tu asesor al cotizar; puedes compartirlo con un familiar o amigo.'
            )
            phone = (q.display_client_phone or '').strip()
            if not phone:
                messages.error(request, 'La cotización no tiene teléfono de cliente.')
                return redirect('store:quotation_review_manage', quotation_id=q.id)
            ok = _notify_whatsapp_n8n(message=share_message, phone=phone, request=request)
            if ok:
                messages.success(request, 'Mensaje de reseña enviado por WhatsApp.')
            else:
                messages.warning(
                    request,
                    'No se pudo enviar por n8n. Usa el botón de WhatsApp manual o copia el mensaje.',
                )
            return redirect('store:quotation_review_manage', quotation_id=q.id)

    plain_code = (review.access_code or '').strip()
    client_link = ''
    if review.access_token:
        client_link = request.build_absolute_uri(
            reverse('store:service_review_unlock', kwargs={'token': str(review.access_token)})
        )

    share_message = ''
    wa_url = ''
    if client_link and review.link_is_active and plain_code:
        share_message = (
            f'Hola {q.display_client_name or ""},\n\n'
            f'Gracias por confiar en MixLab (COT-{q.id}).\n'
            f'Te invitamos a calificar nuestro servicio:\n\n'
            f'Enlace: {client_link}\n'
            f'Código de verificación (abre el formulario): {plain_code}\n\n'
            f'Al terminar recibirás un bono MIX-XXXXXX del '
            f'{settings_obj.review_bonus_percent}% (válido '
            f'{settings_obj.review_bonus_days} días) para canjear con tu asesor.'
        )
        phone = (q.display_client_phone or '').strip()
        if phone:
            wa_url = _wa_me_url(phone, share_message)

    coupon = None
    if review.is_submitted:
        coupon = getattr(review, 'bonus_coupon', None)

    return render(request, 'store/quotation_review_manage.html', {
        'quote': q,
        'review': review,
        'client_link': client_link,
        'plain_code': plain_code,
        'share_message': share_message,
        'wa_url': wa_url,
        'settings_obj': settings_obj,
        'coupon': coupon,
    })


def service_review_unlock(request, token):
    """Cliente: ingresar código de verificación."""
    review = _get_review_by_token(token)
    q = review.quotation

    if not review.link_is_active and not review.is_submitted:
        return render(request, 'store/review_locked.html', {
            'quote': q,
            'review': review,
            'reason': 'expired',
        }, status=403)

    session_key = _session_key(token)
    if request.session.get(session_key):
        if review.is_submitted:
            return redirect('store:service_review_thanks', token=token)
        return redirect('store:service_review_form', token=token)

    # Si ya respondió, permitir ver gracias con el código correcto
    error = ''
    if request.method == 'POST':
        code = (request.POST.get('code') or request.POST.get('password') or '').strip().upper()
        ok = False
        if review.access_code_hash and code:
            ok = check_password(code, review.access_code_hash)
            if not ok and review.access_code:
                ok = code == (review.access_code or '').strip().upper()
        if ok:
            request.session[session_key] = True
            request.session.modified = True
            if review.is_submitted:
                return redirect('store:service_review_thanks', token=token)
            if not review.link_is_active:
                return render(request, 'store/review_locked.html', {
                    'quote': q,
                    'review': review,
                    'reason': 'expired',
                }, status=403)
            return redirect('store:service_review_form', token=token)
        error = 'Código incorrecto. Verifica el mensaje que te enviamos por WhatsApp.'

    return render(request, 'store/review_unlock.html', {
        'quote': q,
        'review': review,
        'token': token,
        'error': error,
    })


def service_review_form(request, token):
    """Formulario de reseña (3 scores + motivo)."""
    review = _get_review_by_token(token)
    q = review.quotation
    session_key = _session_key(token)

    if not request.session.get(session_key):
        return redirect('store:service_review_unlock', token=token)

    if review.is_submitted:
        return redirect('store:service_review_thanks', token=token)

    if not review.link_is_active:
        return render(request, 'store/review_locked.html', {
            'quote': q,
            'review': review,
            'reason': 'expired',
        }, status=403)

    error = ''
    if request.method == 'POST':
        try:
            score_operator = int(request.POST.get('score_operator') or 0)
            score_flavors = int(request.POST.get('score_flavors') or 0)
            score_recommend = int(request.POST.get('score_recommend') or 0)
        except (TypeError, ValueError):
            score_operator = score_flavors = score_recommend = 0
        reason = (request.POST.get('reason') or '').strip()

        if not all(1 <= s <= 10 for s in (score_operator, score_flavors, score_recommend)):
            error = 'Califica cada aspecto con un número del 1 al 10.'
        elif len(reason) < 10:
            error = 'Cuéntanos un poco más: el motivo debe tener al menos 10 caracteres.'
        else:
            settings_obj = SiteSettings.load()
            with transaction.atomic():
                review.score_operator = score_operator
                review.score_flavors = score_flavors
                review.score_recommend = score_recommend
                review.reason = reason[:2000]
                review.submitted_at = timezone.now()
                review.save(update_fields=[
                    'score_operator', 'score_flavors', 'score_recommend',
                    'reason', 'submitted_at', 'updated_at',
                ])
                if not ServiceBonusCoupon.objects.filter(source_review=review).exists():
                    days = getattr(settings_obj, 'review_bonus_days', 60) or 60
                    pct = getattr(settings_obj, 'review_bonus_percent', 15) or 15
                    ServiceBonusCoupon.objects.create(
                        code=_generate_coupon_code(),
                        discount_percent=pct,
                        valid_until=timezone.now() + timedelta(days=days),
                        status='active',
                        source_review=review,
                        source_quotation=q,
                        created_for_name=q.display_client_name or '',
                        created_for_phone=q.display_client_phone or '',
                    )
            return redirect('store:service_review_thanks', token=token)

    return render(request, 'store/review_form.html', {
        'quote': q,
        'review': review,
        'token': token,
        'error': error,
        'score_range': range(1, 11),
    })


def service_review_thanks(request, token):
    """Gracias + código bono (siempre si ya respondió)."""
    from urllib.parse import quote

    review = _get_review_by_token(token)
    q = review.quotation
    session_key = _session_key(token)

    if not request.session.get(session_key):
        return redirect('store:service_review_unlock', token=token)

    if not review.is_submitted:
        return redirect('store:service_review_form', token=token)

    coupon = None
    try:
        coupon = review.bonus_coupon
        coupon.mark_expired_if_needed()
    except ServiceBonusCoupon.DoesNotExist:
        coupon = None

    settings_obj = SiteSettings.load()
    share_message = ''
    share_wa_url = ''
    share_payload = {'title': 'Bono MixLab', 'message': '', 'code': ''}
    if coupon and coupon.status == 'active':
        valid = coupon.valid_until.strftime('%d/%m/%Y') if coupon.valid_until else '—'
        share_message = (
            f'¡Te regalo un bono MixLab! 🎉\n\n'
            f'Código: {coupon.code}\n'
            f'Descuento: {coupon.discount_percent}%\n'
            f'Válido hasta: {valid}\n\n'
            f'Cómo canjearlo: muéstrale este código a tu asesor MixLab '
            f'cuando pidan una cotización. Es de un solo uso '
            f'(no sirve para abrir formularios).'
        )
        share_wa_url = 'https://wa.me/?text=' + quote(share_message)
        share_payload = {
            'title': f'Bono MixLab {coupon.code}',
            'message': share_message,
            'code': coupon.code,
        }

    return render(request, 'store/review_thanks.html', {
        'quote': q,
        'review': review,
        'coupon': coupon,
        'settings_obj': settings_obj,
        'token': token,
        'share_message': share_message,
        'share_wa_url': share_wa_url,
        'share_payload': share_payload,
    })

@transaction.atomic
def redeem_bonus_coupon(quote: Quotation, raw_code: str) -> ServiceBonusCoupon:
    """Valida y canjea un cupón sobre una cotización destino. Aplica % a todas las líneas."""
    code = (raw_code or '').strip().upper()
    if not code:
        raise ValueError('Ingresa un código de bono.')

    coupon = (
        ServiceBonusCoupon.objects
        .select_for_update()
        .filter(code__iexact=code)
        .first()
    )
    if not coupon:
        raise ValueError('Código no encontrado.')

    coupon.mark_expired_if_needed()
    coupon.refresh_from_db()

    if coupon.status == 'redeemed':
        raise ValueError('Este bono ya fue canjeado.')
    if coupon.status == 'expired' or not coupon.is_redeemable:
        raise ValueError('Este bono está vencido.')
    if coupon.source_quotation_id == quote.id:
        raise ValueError('No puedes canjear el bono en la misma cotización que lo originó.')
    if ServiceBonusCoupon.objects.filter(redeemed_on_quotation=quote, status='redeemed').exists():
        raise ValueError('Esta cotización ya tiene un bono canjeado.')

    pct = Decimal(str(coupon.discount_percent))
    factor = (Decimal('100') - pct) / Decimal('100')

    running = Decimal('0.00')
    for item in quote.items.select_for_update():
        list_price = item.list_unit_price if item.list_unit_price is not None else item.unit_price
        list_price = Decimal(str(list_price or 0))
        if item.list_unit_price is None:
            item.list_unit_price = list_price
        new_unit = (list_price * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        item.unit_price = new_unit
        item.subtotal = new_unit * item.quantity
        item.save(update_fields=['list_unit_price', 'unit_price', 'subtotal'])
        running += item.subtotal

    quote.total = running
    quote.save(update_fields=['total', 'updated_at'])

    coupon.status = 'redeemed'
    coupon.redeemed_at = timezone.now()
    coupon.redeemed_on_quotation = quote
    coupon.save(update_fields=['status', 'redeemed_at', 'redeemed_on_quotation'])
    return coupon


@staff_member_required
@require_POST
def quotation_redeem_bonus(request, quotation_id):
    """Staff: aplicar código bono a una cotización."""
    q = get_object_or_404(Quotation, id=quotation_id)
    code = (request.POST.get('bonus_code') or '').strip()
    try:
        coupon = redeem_bonus_coupon(q, code)
        messages.success(
            request,
            f'Bono {coupon.code} aplicado: {coupon.discount_percent}% de descuento en todas las líneas.',
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'No se pudo canjear el bono: {e}')
    return redirect('store:quotation_detail', quotation_id=q.id)
