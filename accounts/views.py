from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .forms import CustomUserCreationForm, UserProfileForm, ShippingAddressForm
from .models import UserProfile, ShippingAddress


def register(request):
    """User registration view"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registro exitoso. Bienvenido!')
            return redirect('store:home')
    else:
        form = CustomUserCreationForm()
    
    context = {
        'form': form,
    }
    return render(request, 'accounts/register.html', context)


@login_required
def profile(request):
    """User profile page"""
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    shipping_addresses = ShippingAddress.objects.filter(user=request.user)
    
    # Handle profile form (phone and default address)
    if request.method == 'POST' and 'profile_form' in request.POST:
        profile_form = UserProfileForm(request.POST, instance=user_profile, user=request.user)
        if profile_form.is_valid():
            # Handle new phone
            new_phone = request.POST.get('new_phone', '').strip()
            if new_phone:
                current_phones = user_profile.phone.split(',') if user_profile.phone else []
                current_phones = [p.strip() for p in current_phones if p.strip()]
                if new_phone not in current_phones:
                    if user_profile.phone:
                        user_profile.phone = f"{user_profile.phone}, {new_phone}"
                    else:
                        user_profile.phone = new_phone
                    user_profile.save()
                    messages.success(request, f'Teléfono {new_phone} agregado exitosamente')
            
            # Save default shipping address
            profile_form.save()
            messages.success(request, 'Perfil actualizado exitosamente')
            return redirect('accounts:profile')
    else:
        profile_form = UserProfileForm(instance=user_profile, user=request.user)
    
    # Handle shipping address form
    if request.method == 'POST' and 'address_form' in request.POST:
        address_form = ShippingAddressForm(request.POST)
        if address_form.is_valid():
            shipping_address = address_form.save(commit=False)
            shipping_address.user = request.user
            shipping_address.save()
            messages.success(request, 'Dirección de envío agregada exitosamente')
            return redirect(reverse('accounts:profile') + '#direcciones')
    else:
        address_form = ShippingAddressForm()
    
    context = {
        'user_profile': user_profile,
        'profile_form': profile_form,
        'address_form': address_form,
        'shipping_addresses': shipping_addresses,
    }
    return render(request, 'accounts/profile.html', context)
