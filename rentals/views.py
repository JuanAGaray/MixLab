from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Rental, RentalAvailability
from store.models import Product


def rental_list(request):
    """List available rental products"""
    rental_products = Product.objects.filter(product_type='rental', available=True)
    
    context = {
        'rental_products': rental_products,
    }
    return render(request, 'rentals/rental_list.html', context)


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
        
        # Calculate duration
        days = (end_date - start_date).days + 1
        duration_quantity = days
        
        if days >= 30:
            duration_type = 'monthly'
            duration_quantity = days // 30
        elif days >= 7:
            duration_type = 'weekly'
            duration_quantity = (days + 6) // 7
        
        # Calculate pricing (using product price as daily rate)
        daily_price = product.price
        rental = Rental(
            user=request.user,
            product=product,
            duration_type=duration_type,
            duration_quantity=duration_quantity,
            start_date=start_date,
            end_date=end_date,
            daily_price=daily_price,
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

