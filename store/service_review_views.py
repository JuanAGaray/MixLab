"""Reseña pública de servicio + cupón bono redimible."""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from datetime import datetime as _dt

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, BooleanField, Case, Count, Exists, ExpressionWrapper, F, FloatField, OuterRef, Q, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    ComboBooking,
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
                f'{settings_obj.review_bonus_days} días) para un evento futuro. '
                f'Puedes usarlo tú o regalárselo a un familiar o amigo; '
                f'se entrega al asesor MixLab al cotizar ese nuevo evento '
                f'(no aplica sobre esta cotización).'
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
            f'{settings_obj.review_bonus_days} días) para un evento futuro '
            f'(tuyo o de un familiar/amigo; no aplica sobre esta cotización).'
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


def _reviews_annotate_type(qs):
    """Añade has_rental / has_booking / is_event / row_avg sin N+1."""
    rental_exists = QuotationItem.objects.filter(
        quotation_id=OuterRef('quotation_id'),
        product__product_type='rental',
    )
    booking_exists = ComboBooking.objects.filter(quotation_id=OuterRef('quotation_id'))
    qs = qs.annotate(
        has_rental=Exists(rental_exists),
        has_booking=Exists(booking_exists),
        row_avg=ExpressionWrapper(
            (F('score_operator') + F('score_flavors') + F('score_recommend')) / 3.0,
            output_field=FloatField(),
        ),
    )
    return qs.annotate(
        is_event=Case(
            When(Q(has_rental=True) | Q(has_booking=True), then=True),
            default=False,
            output_field=BooleanField(),
        ),
    )


@staff_member_required
def service_reviews_dashboard(request):
    """Panel staff: reseñas enviadas, tipo Evento/Producto, promedios y filtros."""
    tipo = (request.GET.get('tipo') or '').strip().lower()
    if tipo not in ('', 'evento', 'producto'):
        tipo = ''
    q_search = (request.GET.get('q') or '').strip()
    orden = (request.GET.get('orden') or 'recientes').strip()
    if orden not in ('recientes', 'peor', 'mejor'):
        orden = 'recientes'
    date_from_raw = (request.GET.get('desde') or '').strip()
    date_to_raw = (request.GET.get('hasta') or '').strip()

    qs = (
        QuotationServiceReview.objects
        .filter(submitted_at__isnull=False)
        .select_related(
            'quotation',
            'quotation__existing_client',
            'bonus_coupon',
        )
    )
    qs = _reviews_annotate_type(qs)

    if date_from_raw:
        try:
            d0 = _dt.strptime(date_from_raw, '%Y-%m-%d').date()
            qs = qs.filter(submitted_at__date__gte=d0)
        except ValueError:
            date_from_raw = ''
    if date_to_raw:
        try:
            d1 = _dt.strptime(date_to_raw, '%Y-%m-%d').date()
            qs = qs.filter(submitted_at__date__lte=d1)
        except ValueError:
            date_to_raw = ''

    if q_search:
        if q_search.isdigit():
            qs = qs.filter(
                Q(quotation_id=int(q_search))
                | Q(quotation__client_name__icontains=q_search)
                | Q(quotation__client_phone__icontains=q_search)
                | Q(quotation__client_email__icontains=q_search)
            )
        else:
            qs = qs.filter(
                Q(quotation__client_name__icontains=q_search)
                | Q(quotation__client_phone__icontains=q_search)
                | Q(quotation__client_email__icontains=q_search)
                | Q(reason__icontains=q_search)
            )

    if tipo == 'evento':
        qs = qs.filter(Q(has_rental=True) | Q(has_booking=True))
    elif tipo == 'producto':
        qs = qs.filter(has_rental=False, has_booking=False)

    if orden == 'peor':
        qs = qs.order_by('row_avg', '-submitted_at')
    elif orden == 'mejor':
        qs = qs.order_by('-row_avg', '-submitted_at')
    else:
        qs = qs.order_by('-submitted_at', '-id')

    agg = qs.aggregate(
        total=Count('id'),
        avg_operator=Avg('score_operator'),
        avg_flavors=Avg('score_flavors'),
        avg_recommend=Avg('score_recommend'),
        count_evento=Count('id', filter=Q(has_rental=True) | Q(has_booking=True)),
        count_producto=Count('id', filter=Q(has_rental=False) & Q(has_booking=False)),
        bonuses_active=Count('id', filter=Q(bonus_coupon__status='active')),
        bonuses_redeemed=Count('id', filter=Q(bonus_coupon__status='redeemed')),
    )

    def _round_avg(value):
        if value is None:
            return None
        return round(float(value), 1)

    avg_op = _round_avg(agg['avg_operator'])
    avg_fl = _round_avg(agg['avg_flavors'])
    avg_rec = _round_avg(agg['avg_recommend'])
    parts = [v for v in (avg_op, avg_fl, avg_rec) if v is not None]
    avg_general = round(sum(parts) / len(parts), 1) if parts else None

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    rows = []
    for review in page_obj.object_list:
        quote = review.quotation
        is_event = bool(getattr(review, 'is_event', False))
        row_avg = getattr(review, 'row_avg', None)
        try:
            coupon = review.bonus_coupon
        except ServiceBonusCoupon.DoesNotExist:
            coupon = None
        rows.append({
            'review': review,
            'quote': quote,
            'tipo': 'evento' if is_event else 'producto',
            'tipo_label': 'Evento' if is_event else 'Producto',
            'row_avg': round(float(row_avg), 1) if row_avg is not None else None,
            'coupon': coupon,
            'client_name': (
                getattr(quote, 'display_client_name', None)
                or (quote.client_name if quote else '')
                or '—'
            ),
            'client_phone': (
                getattr(quote, 'display_client_phone', None)
                or (quote.client_phone if quote else '')
                or ''
            ),
        })

    return render(request, 'store/service_reviews_dashboard.html', {
        'page_obj': page_obj,
        'rows': rows,
        'filter_tipo': tipo,
        'filter_q': q_search,
        'filter_orden': orden,
        'filter_desde': date_from_raw,
        'filter_hasta': date_to_raw,
        'kpis': {
            'total': agg['total'] or 0,
            'avg_general': avg_general,
            'avg_operator': avg_op,
            'avg_flavors': avg_fl,
            'avg_recommend': avg_rec,
            'count_evento': agg['count_evento'] or 0,
            'count_producto': agg['count_producto'] or 0,
            'bonuses_active': agg['bonuses_active'] or 0,
            'bonuses_redeemed': agg['bonuses_redeemed'] or 0,
        },
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
            f'¡Te regalo un bono MixLab para un evento futuro! 🎉\n\n'
            f'Código: {coupon.code}\n'
            f'Descuento: {coupon.discount_percent}%\n'
            f'Válido hasta: {valid}\n\n'
            f'Úsalo en un próximo evento MixLab: muestra el código a tu asesor '
            f'al cotizar. Es de un solo uso y no sirve para abrir formularios '
            f'ni para la cotización que originó el bono.'
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
    """
    Registra el bono en una cotización de evento futuro (distinta a la origen).
    Aplica el % sobre las líneas de esa cotización nueva.
    """
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
        raise ValueError(
            'Este bono es para un evento futuro: no se puede usar en la cotización que lo originó.'
        )
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
            f'Bono {coupon.code} registrado para este evento futuro: '
            f'{coupon.discount_percent}% de descuento en las líneas.',
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'No se pudo registrar el bono: {e}')
    return redirect('store:quotation_detail', quotation_id=q.id)
