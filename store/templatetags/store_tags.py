from django import template
from django.utils import timezone
import json

register = template.Library()

@register.filter(name='split')
def split(value, arg):
    """Split a string by a delimiter"""
    if value:
        return value.split(arg)
    return []


@register.filter
def multiply(value, arg):
    """Multiply the value by the arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def pesos_colombianos(value):
    """Format number as Colombian Pesos"""
    try:
        # Convert to float if it's a string
        if isinstance(value, str):
            value = float(value.replace(',', ''))
        
        # Format with thousand separators
        formatted = f"{value:,.0f}".replace(',', '.')
        return f"${formatted}"
    except (ValueError, TypeError):
        return f"${value}"


@register.filter
def whatsapp_url(value):
    """wa.me desde celular, usuario de WhatsApp, o perfil de usuario."""
    from store.whatsapp import wa_me_url
    if value is None or value == '':
        return '#'
    if hasattr(value, 'profile'):
        try:
            phone = (getattr(value.profile, 'phone', None) or '').strip()
            first = phone.split(',')[0].strip() if phone else ''
            return wa_me_url(first)
        except Exception:
            return ''
    return wa_me_url(value) or '#'


@register.filter
def showcase_rental_prices_json(product):
    """JSON de tarifas de alquiler para el showcase interactivo."""
    if not getattr(product, 'is_rental', False):
        return '[]'
    items = []
    for tariff in product.rental_prices.all():
        if not tariff.is_active:
            continue
        items.append({
            'period': tariff.get_period_type_display(),
            'price': pesos_colombianos(tariff.price),
            'suffix': tariff.period_short_label,
        })
    return json.dumps(items, ensure_ascii=False)


@register.filter
def showcase_attributes_json(product):
    """JSON de atributos del producto para el showcase interactivo."""
    items = []
    for attr in product.attributes.all():
        key = (attr.key or '').strip()
        value = (attr.value or '').strip()
        if key and value:
            items.append({'key': key, 'value': value})
    return json.dumps(items, ensure_ascii=False)


@register.filter
def client_type_display(user):
    """Devuelve el tipo de cliente del perfil del usuario o '—' si no hay perfil."""
    try:
        if user and hasattr(user, 'profile') and user.profile and user.profile.client_type:
            return user.profile.get_client_type_display()
    except Exception:
        pass
    return '—'


@register.filter
def profile_address(user, truncate=None):
    """Devuelve la dirección del perfil del usuario o '—' si no hay perfil o está vacía. truncate=0 para sin truncar."""
    try:
        if user and hasattr(user, 'profile') and user.profile and getattr(user.profile, 'address', ''):
            addr = (user.profile.address or '').strip()
            if addr:
                n = 80 if truncate is None else int(truncate) if truncate else 0
                if n > 0 and len(addr) > n:
                    return addr[:n] + '…'
                return addr
    except Exception:
        pass
    return '—'


@register.filter
def profile_phone(user):
    """Devuelve el teléfono del perfil del usuario o cadena vacía si no hay."""
    try:
        if user and hasattr(user, 'profile') and user.profile:
            return (getattr(user.profile, 'phone', None) or '').strip()
    except Exception:
        pass
    return ''


@register.filter
def phone_whatsapp_url(phone):
    """Convierte celular o usuario a URL de WhatsApp (wa.me)."""
    from store.whatsapp import wa_me_url
    return wa_me_url(phone)


@register.filter
def days_ago(dt):
    """Devuelve antigüedad basado en días. Ej: 'hace 3 días'."""
    if not dt:
        return '—'
    try:
        now = timezone.now()
        # Normalizar naive/aware
        if timezone.is_naive(dt) and timezone.is_aware(now):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        elif timezone.is_aware(dt) and timezone.is_naive(now):
            now = timezone.make_naive(now, timezone.get_current_timezone())
        days = (now.date() - dt.date()).days
        if days <= 0:
            return 'hoy'
        if days == 1:
            return 'hace 1 día'
        return f'hace {days} días'
    except Exception:
        return '—'


@register.filter
def initials(value):
    """Get user initials from User object or username"""
    if hasattr(value, 'first_name') and hasattr(value, 'last_name'):
        first = value.first_name[0].upper() if value.first_name else ''
        last = value.last_name[0].upper() if value.last_name else ''
        if first and last:
            return f"{first}{last}"
    # Fallback to username initials
    if hasattr(value, 'username'):
        username = value.username
        if len(username) >= 2:
            return username[0:2].upper()
        return username[0].upper()
    # If it's just a string
    if isinstance(value, str):
        if len(value) >= 2:
            return value[0:2].upper()
        return value[0].upper()
    return 'U'
