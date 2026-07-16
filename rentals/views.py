from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Rental, RentalAvailability
from store.models import Product, Quotation, QuotationItem


# Cotizaciones con estos estados AÚN NO comprometen la máquina en alquiler.
RENTAL_FREE_ORDER_STATUSES = {
    'sin_respuesta',
    'rechazado',
    'modificado_y_enviado',
}


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
    committed_items = _rental_committed_items_qs()
    out_by_product = {}
    for it in committed_items:
        try:
            qty = int(it.quantity or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        out_by_product[it.product_id] = out_by_product.get(it.product_id, 0) + qty

    if not request.user.is_authenticated or not request.user.is_staff:
        # Catálogo público: mostrar stock efectivo restante
        catalog = []
        for product in rental_products:
            stock = int(product.stock or 0)
            out = int(out_by_product.get(product.id, 0))
            product.effective_stock = max(0, stock - out)
            catalog.append(product)
        return render(request, 'rentals/rental_list.html', {
            'rental_products': catalog,
            'is_manager_dashboard': False,
        })

    stock_rows = []
    total_stock = 0
    total_out = 0
    total_available = 0
    for product in rental_products:
        stock = int(product.stock or 0)
        out = int(out_by_product.get(product.id, 0))
        available = max(0, stock - out)
        total_stock += stock
        total_out += out
        total_available += available
        stock_rows.append({
            'product': product,
            'stock': stock,
            'out': out,
            'available': available,
        })

    pending_quotes = list(_rental_pending_quotes_qs()[:30])
    pending_count = _rental_pending_quotes_qs().count()

    machines_out = []
    for it in committed_items[:40]:
        q = it.quotation
        machines_out.append({
            'item': it,
            'quote': q,
            'product': it.product,
            'quantity': it.quantity,
            'client_name': q.display_client_name or '—',
            'order_status': q.order_status,
            'order_status_display': q.get_order_status_display(),
            'period_label': (
                it.rental_price.get_period_type_display()
                if it.rental_price_id else 'Alquiler'
            ),
            'created_at': q.created_at,
            'updated_at': q.updated_at,
        })
    active_count = sum(int(it.quantity or 0) for it in committed_items)

    return render(request, 'rentals/rental_dashboard.html', {
        'is_manager_dashboard': True,
        'stock_rows': stock_rows,
        'total_stock': total_stock,
        'total_out': total_out,
        'total_available': total_available,
        'pending_count': pending_count,
        'pending_quotes': pending_quotes,
        'machines_out': machines_out,
        'active_count': active_count,
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
    }
    return render(request, 'rentals/rental_detail.html', context)


@login_required
def create_rental(request, product_id):
    """Create a rental booking"""
    product = get_object_or_404(Product, id=product_id, product_type='rental', available=True)
    
    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        duration_type = request.POST.get('duration_type', 'daily')
        contact_name = request.POST.get('contact_name')
        contact_phone = request.POST.get('contact_phone')
        delivery_address = request.POST.get('delivery_address')
        delivery_city = request.POST.get('delivery_city')
        special_requirements = request.POST.get('special_requirements', '')
        
        if not all([start_date_str, end_date_str, contact_name, contact_phone, delivery_address, delivery_city]):
            messages.error(request, 'Por favor completa todos los campos requeridos.')
            return redirect('rentals:rental_detail', product_id=product_id)
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Fechas inválidas.')
            return redirect('rentals:rental_detail', product_id=product_id)
        
        if start_date < timezone.now().date():
            messages.error(request, 'La fecha de inicio no puede ser en el pasado.')
            return redirect('rentals:rental_detail', product_id=product_id)
        
        if end_date <= start_date:
            messages.error(request, 'La fecha de fin debe ser posterior a la fecha de inicio.')
            return redirect('rentals:rental_detail', product_id=product_id)
        
        # Check availability
        conflicting_rentals = Rental.objects.filter(
            product=product,
            status__in=['confirmed', 'active'],
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        if conflicting_rentals.exists():
            messages.error(request, 'El producto no está disponible en las fechas seleccionadas.')
            return redirect('rentals:rental_detail', product_id=product_id)
        
        # Calculate duration and pricing from configured rental tariffs
        unit_price = product.get_rental_price(duration_type)
        if unit_price is None:
            unit_price = product.price

        days = (end_date - start_date).days + 1

        if duration_type == 'hourly':
            try:
                duration_quantity = max(1, int(request.POST.get('hours', 1) or 1))
            except (ValueError, TypeError):
                duration_quantity = 1
        elif duration_type == 'daily':
            duration_quantity = max(1, days)
        elif duration_type == 'weekly':
            duration_quantity = max(1, (days + 6) // 7)
        elif duration_type == 'monthly':
            duration_quantity = max(1, (days + 29) // 30)
        else:
            duration_quantity = max(1, days)
            duration_type = 'daily'

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
        
        messages.success(request, f'Alquiler #{rental.id} creado exitosamente. Estará pendiente de confirmación.')
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

