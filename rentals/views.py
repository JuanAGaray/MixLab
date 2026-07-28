from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import Rental, RentalAvailability
from store.models import Product, Quotation, QuotationItem, SiteSettings
from store.rental_availability import (
    RENTAL_FREE_ORDER_STATUSES,
    build_rental_availability_map,
    rental_committed_units_by_product,
    single_product_availability,
)
from decimal import Decimal


# Cotizaciones con estos estados AÚN NO comprometen la máquina en alquiler.
# Definido en store.rental_availability (RENTAL_FREE_ORDER_STATUSES).


def _rental_committed_items_qs():
    """
    Líneas de alquiler ya alquiladas según cotización:
    cualquier estado distinto de sin respuesta / rechazado / modificado y enviado.
    """
    return (
        QuotationItem.objects
        .filter(product__product_type='rental')
        .exclude(quotation__order_status__in=RENTAL_FREE_ORDER_STATUSES)
        .select_related('quotation', 'product', 'rental_price')
        .order_by('-quotation__updated_at', '-id')
    )


def _rental_pending_quotes_qs():
    """Cotizaciones con máquinas que aún no se consideran alquiladas (solicitudes abiertas)."""
    return (
        Quotation.objects
        .filter(
            items__product__product_type='rental',
            order_status__in=['sin_respuesta', 'modificado_y_enviado'],
        )
        .distinct()
        .prefetch_related('items__product', 'items__rental_price')
        .order_by('-updated_at', '-id')
    )


def _machine_ops_label(order_status: str) -> tuple[str, str]:
    """Estado operativo de la máquina según el pedido. (label, bootstrap color)."""
    mapping = {
        'aceptado': ('Reservada', 'info'),
        'esperando_pago': ('Reservada · espera pago', 'warning'),
        'pago_parcial': ('En cliente · pago incompleto', 'warning'),
        'pago_recibido': ('En operación', 'success'),
        'enviado': ('Enviada / en tránsito', 'primary'),
        'recibido': ('En cliente', 'success'),
        'modificado_y_enviado': ('En revisión', 'secondary'),
        'sin_respuesta': ('Solicitud', 'secondary'),
        'rechazado': ('Liberada', 'dark'),
    }
    return mapping.get(order_status, (order_status or '—', 'secondary'))


def _combo_booking_status(booking, order_status: str, today) -> tuple[str, str, str, bool]:
    """
    Estado de máquina / periodo para agendas de combo (evento).
    No trata un evento futuro como 'ya alquilado / en cliente'.
    Returns: (machine_label, color, period_display, is_future)
    """
    event = booking.event_date
    event_label = event.strftime('%d/%m/%Y')
    time_bit = ''
    if getattr(booking, 'event_time', None):
        time_bit = f' {booking.event_time.strftime("%H:%M")}'

    if booking.status == 'cancelado':
        return ('Cancelado', 'dark', f'Evento cancelado · {event_label}', False)

    if event > today:
        days = (event - today).days
        period = f'Agendado · evento {event_label}{time_bit} (en {days} día{"s" if days != 1 else ""})'
        if order_status in ('pago_parcial', 'esperando_pago'):
            return ('Agendada · falta saldo', 'warning', period, True)
        if order_status in ('pago_recibido', 'aceptado', 'enviado', 'recibido'):
            return ('Agendada · confirmada', 'info', period, True)
        return ('Agendada', 'info', period, True)

    if event == today:
        period = f'Evento hoy · {event_label}{time_bit}'
        if order_status == 'pago_parcial':
            return ('Evento hoy · pago incompleto', 'warning', period, False)
        if order_status in ('enviado',):
            return ('En tránsito · evento hoy', 'primary', period, False)
        return ('En evento', 'success', period, False)

    # Evento ya pasó: no inventar "X días en alquiler" como si fuera contrato continuo
    ago = (today - event).days
    period = f'Evento {event_label} · hace {ago} día{"s" if ago != 1 else ""}'
    if order_status == 'pago_parcial':
        return ('Post-evento · saldo pendiente', 'warning', period, False)
    if order_status in ('enviado', 'recibido', 'pago_recibido'):
        return ('Post-evento · pendiente cierre', 'secondary', period, False)
    return ('Post-evento', 'secondary', period, False)


def _estimate_next_payment(quote: Quotation, period_type: str | None, today):
    """
    Estima próximo cobro:
    - Si hay saldo: cobrar saldo (hoy / urgente).
    - Si está al día y el periodo es semanal/mensual: siguiente ciclo desde último pago o creación.
    """
    remaining = quote.remaining_balance
    if remaining and remaining > 0:
        return {
            'date': today,
            'label': 'Saldo pendiente',
            'amount': remaining,
            'urgent': True,
            'is_balance': True,
        }

    if quote.order_status not in (
        'pago_parcial', 'pago_recibido', 'enviado', 'recibido', 'aceptado', 'esperando_pago',
    ):
        return None

    last_pay = None
    try:
        last_pay = quote.payments.order_by('-created_at', '-id').first()
    except Exception:
        last_pay = None
    base = (last_pay.created_at.date() if last_pay else quote.created_at.date())

    period = (period_type or '').strip()
    if period == 'monthly':
        nxt = base + timedelta(days=30)
        return {
            'date': nxt,
            'label': 'Renovación mensual',
            'amount': None,
            'urgent': nxt <= today,
            'is_balance': False,
        }
    if period == 'weekly':
        nxt = base + timedelta(days=7)
        return {
            'date': nxt,
            'label': 'Renovación semanal',
            'amount': None,
            'urgent': nxt <= today,
            'is_balance': False,
        }
    if period == 'daily':
        nxt = base + timedelta(days=1)
        return {
            'date': nxt,
            'label': 'Ciclo diario',
            'amount': None,
            'urgent': nxt <= today,
            'is_balance': False,
        }
    return None


def _build_client_rental_rows(today):
    """
    Filas de estado por cliente/cotización con máquinas de alquiler activas.
    """
    quotes = (
        Quotation.objects
        .filter(items__product__product_type='rental')
        .exclude(order_status__in=RENTAL_FREE_ORDER_STATUSES)
        .exclude(order_status='rechazado')
        .distinct()
        .select_related('existing_client', 'created_by')
        .prefetch_related(
            'items__product',
            'items__rental_price',
            'payments',
            'combo_booking',
        )
        .order_by('-updated_at', '-id')
    )

    rows = []
    for q in quotes[:80]:
        rental_items = [
            it for it in q.items.all()
            if it.product_id and getattr(it.product, 'product_type', '') == 'rental'
        ]
        if not rental_items:
            continue

        machines = []
        primary_period = None
        for it in rental_items:
            period_label = 'Alquiler'
            period_type = None
            if it.rental_price_id:
                period_label = it.rental_price.get_period_type_display()
                period_type = it.rental_price.period_type
                if not primary_period:
                    primary_period = period_type
            machines.append({
                'name': it.product.name,
                'quantity': it.quantity,
                'period_label': period_label,
                'serial': getattr(it.product, 'rental_serial', '') or '',
            })

        start_ref = q.created_at.date()
        booking = None
        try:
            booking = q.combo_booking
        except Exception:
            booking = None

        is_combo_event = bool(booking and getattr(booking, 'event_date', None))
        is_future_booking = False
        date_caption = 'Desde'

        if is_combo_event:
            start_ref = booking.event_date
            machine_label, machine_color, period_display, is_future_booking = _combo_booking_status(
                booking, q.order_status, today,
            )
            date_caption = 'Evento'
            # En agendas: el ítem no es un alquiler continuo por periodo
            for m in machines:
                m['period_label'] = 'Combo / evento'
            elapsed_days = 0 if is_future_booking else max(0, (today - start_ref).days)
        else:
            elapsed_days = max(0, (today - start_ref).days)
            machine_label, machine_color = _machine_ops_label(q.order_status)
            if primary_period == 'monthly':
                period_display = f'Mensual · {elapsed_days} día{"s" if elapsed_days != 1 else ""}'
            elif primary_period == 'weekly':
                period_display = f'Semanal · {elapsed_days} día{"s" if elapsed_days != 1 else ""}'
            elif primary_period == 'daily':
                period_display = f'Diario · {elapsed_days} día{"s" if elapsed_days != 1 else ""}'
            elif primary_period == 'hourly':
                period_display = f'Por hora · desde {start_ref.strftime("%d/%m/%Y")}'
            else:
                period_display = f'{elapsed_days} día{"s" if elapsed_days != 1 else ""} en alquiler'

        next_pay = _estimate_next_payment(q, None if is_combo_event else primary_period, today)
        # Saldo de un evento futuro: cobro pendiente, pero no "máquina ya en cliente"
        if next_pay and next_pay.get('is_balance') and is_future_booking:
            next_pay = {
                **next_pay,
                'label': 'Saldo por cobrar (evento pendiente)',
                # Solo marcar urgente si el evento está cerca (7 días) o ya pasó el cobro esperado
                'urgent': (booking.event_date - today).days <= 7,
            }

        phone = (q.display_client_phone or '').strip()
        rows.append({
            'quote': q,
            'client_name': q.display_client_name or '—',
            'client_phone': phone,
            'machines': machines,
            'machines_summary': ', '.join(
                f'{m["name"]}' + (f' ×{m["quantity"]}' if m["quantity"] > 1 else '')
                for m in machines
            ),
            'order_status': q.order_status,
            'order_status_display': q.get_order_status_display(),
            'machine_status': machine_label,
            'machine_status_color': machine_color,
            'period_display': period_display,
            'start_date': start_ref,
            'date_caption': date_caption,
            'elapsed_days': elapsed_days,
            'is_combo_event': is_combo_event,
            'is_future_booking': is_future_booking,
            'booking_status': booking.status if booking else '',
            'booking_id': booking.id if booking else None,
            'total': q.total,
            'amount_paid': q.amount_paid,
            'remaining': q.remaining_balance,
            'next_payment': next_pay,
            'updated_at': q.updated_at,
        })

    # Priorizar: alquileres/eventos actuales con saldo, luego agendas futuras, luego recientes
    def sort_key(row):
        nxt = row.get('next_payment')
        future = 1 if row.get('is_future_booking') else 0
        urgent = 0 if (nxt and nxt.get('urgent') and not row.get('is_future_booking')) else 1
        remaining = 0 if (row.get('remaining') or 0) > 0 else 1
        return (future, urgent, remaining, -(row['updated_at'].timestamp() if row.get('updated_at') else 0))

    rows.sort(key=sort_key)
    return rows


def rental_list(request):
    """
    /rentals/
    - Staff: dashboard con stock, solicitudes (cotizaciones) y máquinas en alquiler.
    - Público: catálogo de máquinas para reservar.
    """
    today = timezone.now().date()
    rental_products = (
        Product.objects.filter(product_type='rental', available=True)
        .prefetch_related('rental_prices')
        .order_by('name')
    )

    # Unidades ocupadas por producto según cotizaciones comprometidas
    out_by_product = rental_committed_units_by_product()

    if not request.user.is_authenticated or not request.user.is_staff:
        # Catálogo público: stock efectivo (cotizaciones + combos)
        avail_map = build_rental_availability_map(rental_products, out_by_product)
        catalog = []
        for product in rental_products:
            metrics = avail_map.get(product.id, {})
            product.effective_stock = metrics.get('available', 0)
            product.combo_reserved = metrics.get('combo_total', 0)
            catalog.append(product)
        return render(request, 'rentals/rental_list.html', {
            'rental_products': catalog,
            'is_manager_dashboard': False,
        })

    avail_map = build_rental_availability_map(rental_products, out_by_product)
    stock_rows = []
    total_stock = 0
    total_out = 0
    total_combo = 0
    total_available = 0
    for product in rental_products:
        metrics = avail_map.get(product.id, {})
        stock = metrics['stock']
        out = metrics['out']
        combo_reserved = metrics['combo_total']
        available = metrics['available']
        total_stock += stock
        total_out += out
        total_combo += combo_reserved
        total_available += available
        stock_rows.append({
            'product': product,
            'stock': stock,
            'out': out,
            'combo_reserved': combo_reserved,
            'combo_fixed': metrics.get('combo_fixed', 0),
            'combo_category': metrics.get('combo_category', 0),
            'available': available,
        })

    pending_quotes = list(_rental_pending_quotes_qs()[:30])
    pending_count = _rental_pending_quotes_qs().count()

    committed_items = _rental_committed_items_qs()
    machines_out = []
    for it in committed_items[:40]:
        q = it.quotation
        booking = None
        try:
            booking = q.combo_booking
        except Exception:
            booking = None

        order_status_display = q.get_order_status_display()
        period_label = (
            it.rental_price.get_period_type_display()
            if it.rental_price_id else 'Alquiler'
        )
        if booking and getattr(booking, 'event_date', None):
            if getattr(booking, 'status', '') == 'cancelado':
                continue

            event_lbl = booking.event_date.strftime('%d/%m/%Y')
            period_label = f'Combo · {event_lbl}'

            if booking.event_date > today:
                order_status_display = 'Combo agendado'
                if q.order_status in ('pago_parcial', 'esperando_pago'):
                    order_status_display = 'Combo agendado · pago incompleto'
                elif q.order_status in ('pago_recibido', 'aceptado', 'enviado', 'recibido'):
                    order_status_display = 'Combo agendado · confirmado'
            elif booking.event_date == today:
                order_status_display = 'Combo en evento · hoy'
            else:
                order_status_display = 'Combo post-evento'

        machines_out.append({
            'item': it,
            'quote': q,
            'product': it.product,
            'quantity': it.quantity,
            'client_name': q.display_client_name or '—',
            'order_status': q.order_status,
            'order_status_display': order_status_display,
            'period_label': period_label,
            'created_at': q.created_at,
            'updated_at': q.updated_at,
        })
    active_count = sum(int(it.quantity or 0) for it in committed_items)

    client_status_rows = _build_client_rental_rows(today)
    overdue_count = sum(
        1 for r in client_status_rows
        if r.get('next_payment') and r['next_payment'].get('urgent')
    )

    return render(request, 'rentals/rental_dashboard.html', {
        'is_manager_dashboard': True,
        'stock_rows': stock_rows,
        'total_stock': total_stock,
        'total_out': total_out,
        'total_combo': total_combo,
        'total_available': total_available,
        'pending_count': pending_count,
        'pending_quotes': pending_quotes,
        'machines_out': machines_out,
        'active_count': active_count,
        'client_status_rows': client_status_rows,
        'overdue_count': overdue_count,
        'today': today,
        'order_status_choices': Quotation.ORDER_STATUS_CHOICES,
    })


def rental_detail(request, product_id):
    """Rental product detail and booking"""
    product = get_object_or_404(Product, id=product_id, product_type='rental', available=True)
    
    # Get availability for next 90 days
    today = timezone.now().date()
    end_date = today + timedelta(days=90)
    
    # Check existing rentals
    active_rentals = Rental.objects.filter(
        product=product,
        status__in=['confirmed', 'active'],
        end_date__gte=today
    )
    
    unavailable_dates = set()
    for rental in active_rentals:
        current_date = rental.start_date
        while current_date <= rental.end_date:
            unavailable_dates.add(current_date)
            current_date += timedelta(days=1)
    
    context = {
        'product': product,
        'rental_prices': product.rental_prices.filter(is_active=True),
        'unavailable_dates': unavailable_dates,
        'today': today.isoformat(),
        'max_date': end_date.isoformat(),
        'availability': single_product_availability(product),
    }
    return render(request, 'rentals/rental_detail.html', context)


def _product_document_context(product: Product) -> dict:
    """Contexto compartido para formatos de contrato / acta de muestra."""
    settings_obj = SiteSettings.load()
    tariffs = product.rental_prices.filter(is_active=True).order_by('order', 'period_type')
    commercial = product.rental_commercial_value
    deposit_8pct = None
    if commercial is not None and commercial > 0:
        deposit_8pct = (Decimal(str(commercial)) * Decimal('0.08')).quantize(Decimal('0.01'))
    return {
        'product': product,
        'settings': settings_obj,
        'tariffs': tariffs,
        'commercial_value': commercial,
        'deposit_8pct': deposit_8pct,
    }


@xframe_options_sameorigin
def rental_sample_contract(request, product_id):
    """Formato de muestra del contrato de alquiler para una máquina."""
    product = get_object_or_404(Product, id=product_id, product_type='rental', available=True)
    return render(request, 'rentals/sample_contract.html', _product_document_context(product))


@xframe_options_sameorigin
def rental_sample_delivery_acta(request, product_id):
    """Formato de muestra del acta de entrega / recepción."""
    product = get_object_or_404(Product, id=product_id, product_type='rental', available=True)
    return render(request, 'rentals/sample_delivery_acta.html', _product_document_context(product))


@login_required
def create_rental(request, product_id):
    """Create a rental booking (solicitud) desde tipo de alquiler, sin fechas del cliente."""
    product = get_object_or_404(Product, id=product_id, product_type='rental', available=True)

    if request.method == 'POST':
        avail = single_product_availability(product)
        if avail['available'] <= 0:
            messages.error(
                request,
                'Esta máquina no tiene unidades disponibles para alquiler individual '
                '(puede estar reservada para combos o en cotizaciones activas).',
            )
            return redirect('rentals:rental_detail', product_id=product_id)

        duration_type = (request.POST.get('duration_type') or 'daily').strip()
        special_requirements = (request.POST.get('special_requirements') or '').strip()

        allowed_types = {c[0] for c in Rental.DURATION_CHOICES}
        active_tariffs = set(
            product.rental_prices.filter(is_active=True).values_list('period_type', flat=True)
        )
        if active_tariffs and duration_type not in active_tariffs:
            messages.error(request, 'Selecciona un tipo de alquiler válido para esta máquina.')
            return redirect('rentals:rental_detail', product_id=product_id)
        if duration_type not in allowed_types:
            duration_type = 'daily'

        try:
            duration_quantity = max(1, int(request.POST.get('duration_quantity', 1) or 1))
        except (ValueError, TypeError):
            duration_quantity = 1

        # Fechas internas estimadas (se coordinan luego con el cliente)
        start_date = timezone.now().date()
        if duration_type == 'hourly':
            end_date = start_date
        elif duration_type == 'weekly':
            end_date = start_date + timedelta(days=(duration_quantity * 7) - 1)
        elif duration_type == 'monthly':
            end_date = start_date + timedelta(days=(duration_quantity * 30) - 1)
        else:
            duration_type = 'daily'
            end_date = start_date + timedelta(days=max(0, duration_quantity - 1))

        unit_price = product.get_rental_price(duration_type)
        if unit_price is None:
            unit_price = product.price

        # Contacto desde el perfil del usuario (no se pide en el form público)
        profile = getattr(request.user, 'profile', None)
        contact_name = (request.user.get_full_name() or request.user.username or '').strip() or 'Cliente'
        contact_phone = (getattr(profile, 'phone', None) or '').strip() or 'Por confirmar'
        delivery_address = (getattr(profile, 'address', None) or '').strip() or 'Por confirmar'
        delivery_city = (getattr(profile, 'city', None) or '').strip() or 'Por confirmar'

        rental = Rental(
            user=request.user,
            product=product,
            duration_type=duration_type,
            duration_quantity=duration_quantity,
            start_date=start_date,
            end_date=end_date,
            daily_price=unit_price,
            contact_name=contact_name,
            contact_phone=contact_phone,
            delivery_address=delivery_address,
            delivery_city=delivery_city,
            special_requirements=special_requirements,
        )
        rental.total_price = rental.calculate_total()
        rental.save()

        messages.success(
            request,
            f'Solicitud de alquiler #{rental.id} creada. El equipo MixLab te contactará para '
            f'coordinar fechas, contrato y documentación.',
        )
        return redirect('rentals:rental_detail_view', rental_id=rental.id)

    return redirect('rentals:rental_detail', product_id=product_id)


@login_required
def rental_detail_view(request, rental_id):
    """View rental details"""
    rental = get_object_or_404(Rental, id=rental_id, user=request.user)
    context = {
        'rental': rental,
    }
    return render(request, 'rentals/rental_detail_view.html', context)


@login_required
def rental_history(request):
    """User's rental history"""
    rentals = Rental.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'rentals': rentals,
    }
    return render(request, 'rentals/rental_history.html', context)


@staff_member_required
def rental_requests(request):
    """Manager: listado de todas las solicitudes de alquiler."""
    rentals = Rental.objects.select_related('user', 'product').order_by('-created_at')

    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()

    if q:
        rentals = rentals.filter(
            Q(id__icontains=q)
            | Q(contact_name__icontains=q)
            | Q(contact_phone__icontains=q)
            | Q(product__name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )
    if status in dict(Rental.STATUS_CHOICES):
        rentals = rentals.filter(status=status)

    paginator = Paginator(rentals, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'status_choices': Rental.STATUS_CHOICES,
        'filter_q': q,
        'filter_status': status,
        'pending_count': Rental.objects.filter(status='pending').count(),
    }
    return render(request, 'rentals/rental_requests.html', context)


@staff_member_required
def rental_request_detail(request, rental_id):
    """Manager: detalle de una solicitud de alquiler."""
    rental = get_object_or_404(Rental.objects.select_related('user', 'product'), id=rental_id)

    if request.method == 'POST':
        new_status = (request.POST.get('status') or '').strip()
        if new_status in dict(Rental.STATUS_CHOICES):
            rental.status = new_status
            if new_status == 'confirmed' and not rental.confirmed_at:
                rental.confirmed_at = timezone.now()
            if new_status == 'completed' and not rental.completed_at:
                rental.completed_at = timezone.now()
            rental.save()
            messages.success(request, f'Solicitud #{rental.id} actualizada a “{rental.get_status_display()}”.')
            return redirect('rentals:rental_request_detail', rental_id=rental.id)
        messages.error(request, 'Estado inválido.')

    context = {
        'rental': rental,
        'status_choices': Rental.STATUS_CHOICES,
    }
    return render(request, 'rentals/rental_request_detail.html', context)


@staff_member_required
def rental_request_set_status(request, rental_id):
    """Manager: cambiar estado desde el listado (POST)."""
    rental = get_object_or_404(Rental, id=rental_id)
    if request.method != 'POST':
        return redirect('rentals:rental_requests')

    new_status = (request.POST.get('status') or '').strip()
    if new_status not in dict(Rental.STATUS_CHOICES):
        messages.error(request, 'Estado inválido.')
        return redirect('rentals:rental_requests')

    rental.status = new_status
    if new_status == 'confirmed' and not rental.confirmed_at:
        rental.confirmed_at = timezone.now()
    if new_status == 'completed' and not rental.completed_at:
        rental.completed_at = timezone.now()
    rental.save(update_fields=['status', 'confirmed_at', 'completed_at', 'updated_at'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'status': rental.status,
            'status_display': rental.get_status_display(),
        })

    messages.success(request, f'Solicitud #{rental.id} → {rental.get_status_display()}')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('rentals:rental_requests')

