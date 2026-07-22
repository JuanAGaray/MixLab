import os
import logging
import json
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.contrib import messages
import base64
import re
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Min, Max, Sum, Prefetch
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from decimal import Decimal

from .models import (
    Product, Category, Cart, CartItem, Order, OrderItem,
    ProductImage, ProductVariation, ProductVariationImage, ProductTechnicalSpec, ProductAttribute,
    ProductRentalPrice,
    DilutionBaseProduct, SiteSettings, PaymentMethod,
    RentalContractRequirements, RentalDeliveryActa,
    FinanceRecord,
    DrinzzContractConfig,
)
from .forms import (
    ProductForm,
    ProductImageForm,
    ProductVariationForm,
    ProductVariationImageForm,
    ProductTechnicalSpecForm,
    CategoryForm,
    ProductAttributeForm,
    QuotationForm,
    GuestCheckoutForm,
    DilutionBaseProductForm,
    SiteSettingsForm,
    PaymentMethodForm,
    DrinzzContractConfigForm,
)
from .models import Quotation, QuotationItem

# IVA en Colombia (por defecto 19%). Los precios ya incluyen IVA en este proyecto.
IVA_RATE = Decimal('0.19')

logger = logging.getLogger(__name__)


def _stock_commit_statuses():
    """Estados de pedido que comprometen inventario (descuentan stock una sola vez)."""
    return {
        'aceptado',
        'esperando_pago',
        'pago_parcial',
        'pago_recibido',
        'enviado',
        'recibido',
        'modificado_y_enviado',
    }


def _post_payment_statuses():
    """Estados que implican comprobante / pago (o posteriores)."""
    return {
        'pago_parcial',
        'pago_recibido',
        'enviado',
        'recibido',
        'modificado_y_enviado',
    }


def _fully_paid_statuses():
    """Estados con pago total (cotización cerrada / factura disponible)."""
    return {
        'pago_recibido',
        'enviado',
        'recibido',
        'modificado_y_enviado',
    }


def _close_quotation_on_full_payment(quote: Quotation) -> bool:
    """Marca la cotización como cerrada cuando el pago es total. Devuelve True si cambió."""
    changed = False
    if quote.quotation_status != 'cerrada':
        quote.quotation_status = 'cerrada'
        changed = True
    return changed


def _quotation_is_fully_paid(quote: Quotation) -> bool:
    return quote.order_status in _fully_paid_statuses() and bool(quote.payment_proof)


def _quotation_can_edit(quote: Quotation) -> bool:
    """Permite reabrir cotizaciones no canceladas / no pagadas / no cerradas."""
    if not quote:
        return False
    if quote.quotation_status in ('cancelada', 'cerrada'):
        return False
    if quote.order_status in _fully_paid_statuses():
        return False
    return True


def _restore_stock_for_quotation(quotation: Quotation) -> bool:
    """
    Devuelve al inventario el stock previamente descontado de una cotización.
    No toca productos de alquiler. Limpia el flag stock_deducted.
    """
    if not getattr(quotation, 'stock_deducted', False):
        return False

    items = quotation.items.select_related('product')
    changed_any = False
    for it in items:
        product = it.product
        if not product:
            continue
        if getattr(product, 'is_rental', False) or getattr(product, 'product_type', '') == 'rental':
            continue
        try:
            qty = int(it.quantity or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        current_stock = int(product.stock or 0)
        new_stock = current_stock + qty
        if new_stock != current_stock:
            product.stock = new_stock
            product.save(update_fields=['stock'])
            changed_any = True

    quotation.stock_deducted = False
    quotation.save(update_fields=['stock_deducted', 'updated_at'])
    return changed_any


def _quote_discount_from_saved_item(item) -> tuple[str, float]:
    """Reconstruye descuento de línea (tipo/valor) a partir de precios guardados."""
    try:
        unit = Decimal(str(item.unit_price or 0))
    except Exception:
        unit = Decimal('0.00')
    try:
        list_unit = item.list_unit_price
        if list_unit is None:
            list_unit = unit
        else:
            list_unit = Decimal(str(list_unit))
    except Exception:
        list_unit = unit
    if list_unit <= 0 or unit >= list_unit:
        return 'percent', 0.0
    amount = (list_unit - unit).quantize(Decimal('0.01'))
    return 'amount', float(amount)


def _load_quotation_into_session(request, quote: Quotation) -> dict:
    """Carga ítems de una cotización guardada en la sesión del builder."""
    session_quote: dict = {}
    for item in quote.items.select_related('product', 'rental_price').all():
        if not item.product_id:
            continue
        rental_price_id = item.rental_price_id
        if rental_price_id:
            line_key = f'{item.product_id}:{rental_price_id}'
        else:
            line_key = str(item.product_id)
        dtype, dval = _quote_discount_from_saved_item(item)
        session_quote[line_key] = {
            'qty': int(item.quantity or 1),
            'discount_type': dtype,
            'discount_value': dval,
            'discount_percent': dval if dtype == 'percent' else 0.0,
            'rental_price_id': rental_price_id,
        }
    request.session['quotation'] = session_quote
    request.session['editing_quotation_id'] = quote.id
    request.session.modified = True
    return session_quote


def _clear_quotation_edit_session(request):
    request.session.pop('editing_quotation_id', None)
    request.session['quotation'] = {}
    request.session.modified = True


def _deduct_stock_for_quotation(quotation: Quotation):
    """
    Descontar stock de los productos de una cotización.
    Se ejecuta una sola vez (flag stock_deducted), al aceptar el pedido o al
    pasar a un estado posterior que también compromete inventario.
    No descuenta productos de alquiler.
    """
    if getattr(quotation, 'stock_deducted', False):
        return False

    items = quotation.items.select_related('product')
    changed_any = False
    for it in items:
        product = it.product
        if not product:
            continue
        # Alquiler no reduce stock de inventario de venta
        if getattr(product, 'is_rental', False) or getattr(product, 'product_type', '') == 'rental':
            continue
        try:
            qty = int(it.quantity or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        current_stock = int(product.stock or 0)
        new_stock = current_stock - qty
        if new_stock < 0:
            new_stock = 0
        if new_stock != current_stock:
            product.stock = new_stock
            product.save(update_fields=['stock'])
            changed_any = True

    quotation.stock_deducted = True
    quotation.save(update_fields=['stock_deducted', 'updated_at'])
    return changed_any


def _ensure_stock_deducted_for_committed_quotations():
    """Sincroniza stock pendiente de cotizaciones ya aceptadas/pagadas sin descuento."""
    pending = Quotation.objects.filter(
        stock_deducted=False,
        order_status__in=_stock_commit_statuses(),
    ).prefetch_related('items__product')
    for quote in pending:
        _deduct_stock_for_quotation(quote)


def home(request):
    """Home page with featured products"""
    from django.utils import timezone
    from datetime import timedelta

    featured_products = list(Product.objects.filter(available=True).select_related('category')[:8])
    total_products = Product.objects.filter(available=True).count()
    now = timezone.now()
    recent_cutoff = now - timedelta(days=30)

    # Get cart quantities for authenticated users
    cart_quantities = {}
    if request.user.is_authenticated:
        try:
            cart_obj = Cart.objects.get(user=request.user)
            for item in cart_obj.items.all():
                cart_quantities[item.product.id] = item.quantity
        except Cart.DoesNotExist:
            pass
    else:
        session_cart = request.session.get('cart', {})
        for product_id_str, quantity in session_cart.items():
            try:
                product_id = int(product_id_str)
                cart_quantities[product_id] = quantity
            except (ValueError, TypeError):
                continue

    for i, product in enumerate(featured_products):
        product.cart_quantity = cart_quantities.get(product.id, 0)
        if product.has_discount:
            product.display_badge = 'Oferta'
            product.display_badge_class = 'badge-offer'
        elif product.created_at >= recent_cutoff:
            product.display_badge = 'Nuevo'
            product.display_badge_class = 'badge-new'
        elif i < 2:
            product.display_badge = 'Más vendido'
            product.display_badge_class = 'badge-bestseller'
        else:
            product.display_badge = ''
            product.display_badge_class = ''

    product_prefetch = Prefetch(
        'products',
        queryset=(
            Product.objects
            .prefetch_related('rental_prices', 'attributes')
            .order_by('-available', '-created_at')[:10]
        ),
        to_attr='preview_products',
    )
    category_showcases = list(
        Category.objects.prefetch_related(product_prefetch).order_by('name')[:8]
    )
    category_showcases = [c for c in category_showcases if c.preview_products]

    context = {
        'featured_products': featured_products,
        'total_products': total_products,
        'total_clients': 100,
        'category_showcases': category_showcases,
    }
    return render(request, 'store/home.html', context)


def about(request):
    """Página 'Quiénes somos'."""
    return render(request, 'store/about.html')


def privacy_policy(request):
    """Página de políticas de privacidad."""
    return render(request, 'store/privacy_policy.html')


def normatividad(request):
    """Página de normatividad y cumplimiento legal."""
    return render(request, 'store/normatividad.html')


def alianza_biztra(request):
    """Detalle de alianza MixLab × Biztra."""
    return render(request, 'store/alianza_biztra.html')


def alianza_drinzz(request):
    """Detalle de alianza / modelo Drinzz (punto de granizados)."""
    contract = DrinzzContractConfig.load()
    return render(request, 'store/alianza_drinzz.html', {
        'drinzz_contract': contract,
    })


def alianzas(request):
    """Listado de alianzas estratégicas de MixLab."""
    alliances = [
        {
            'slug': 'biztra',
            'name': 'Biztra',
            'tagline': 'Sistema integral para el control y crecimiento de tu negocio',
            'badge': 'Nueva alianza',
            'benefit': '1 mes gratis por compras acumuladas > $490.000',
            'icon': 'bi-graph-up-arrow',
            'logo': 'img/logo-biztra-clear.png',
            'url_name': 'store:alianza_biztra',
            'active': True,
        },
        {
            'slug': 'drinzz',
            'name': 'Drinzz',
            'tagline': 'Toda la infraestructura para un punto de granizados en tu local',
            'badge': 'Modelo de negocio',
            'benefit': 'Desde 20/80 · sube a 30/70 + bono 10% · $500.000 a $3.500.000',
            'icon': 'bi-cup-straw',
            'logo': 'img/logo-drinzz-clear.png',
            'url_name': 'store:alianza_drinzz',
            'active': True,
        },
    ]
    return render(request, 'store/alianzas.html', {'alliances': alliances})


def product_list(request):
    """Catálogo de productos (tienda) con filtros y ordenamiento."""
    products = Product.objects.filter(available=True)

    # --- Filtros básicos ---
    category_slug = request.GET.get('category', '').strip()
    search_query = request.GET.get('q', '').strip()

    if category_slug:
        products = products.filter(category__slug=category_slug)

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(keywords__icontains=search_query)
        )

    # --- Filtro por precio ---
    min_price_param = request.GET.get('min_price', '').strip()
    max_price_param = request.GET.get('max_price', '').strip()

    try:
        min_price = Decimal(min_price_param) if min_price_param else None
    except (ArithmeticError, ValueError):
        min_price = None

    try:
        max_price = Decimal(max_price_param) if max_price_param else None
    except (ArithmeticError, ValueError):
        max_price = None

    # Solo aplicar filtro de precio si es mayor que 0 (0 = sin filtro)
    if min_price is not None and min_price > 0:
        products = products.filter(price__gte=min_price)
    if max_price is not None and max_price > 0:
        products = products.filter(price__lte=max_price)

    # --- Filtro por atributo ---
    attr_key_param = request.GET.get('attr_key', '').strip()
    attr_value_param = request.GET.get('attr_value', '').strip()
    if attr_key_param and attr_value_param:
        products = products.filter(
            attributes__key=attr_key_param,
            attributes__value=attr_value_param
        ).distinct()

    # --- Ordenamiento ---
    order = request.GET.get('order', '').strip()
    if order == 'price_asc':
        products = products.order_by('price')
    elif order == 'price_desc':
        products = products.order_by('-price')
    elif order == 'name_asc':
        products = products.order_by('name')
    elif order == 'name_desc':
        products = products.order_by('-name')
    else:
        products = products.order_by('-created_at')

    # --- Cantidades en carrito (igual que en home) ---
    cart_quantities: dict[int, int] = {}
    if request.user.is_authenticated:
        try:
            cart_obj = Cart.objects.get(user=request.user)
            for item in cart_obj.items.all():
                cart_quantities[item.product.id] = item.quantity
        except Cart.DoesNotExist:
            pass
    else:
        session_cart = request.session.get('cart', {})
        for product_id_str, quantity in session_cart.items():
            try:
                product_id = int(product_id_str)
                cart_quantities[product_id] = quantity
            except (ValueError, TypeError):
                continue

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Presentaciones (variaciones tipo 'presentation') para productos de la página
    product_ids = [p.id for p in page_obj]
    presentations_map: dict[int, str] = {}
    if product_ids:
        for var in ProductVariation.objects.filter(
            product_id__in=product_ids, variation_type='presentation', available=True
        ).order_by('product_id'):
            if var.product_id not in presentations_map:
                presentations_map[var.product_id] = var.value

    for product in page_obj:
        product.cart_quantity = cart_quantities.get(product.id, 0)
        product.presentation_value = presentations_map.get(product.id)

    # Categorías con conteo
    category_qs = Category.objects.annotate(
        product_count=Count('products', filter=Q(products__available=True))
    )

    # Rango global de precios
    price_range = Product.objects.filter(available=True).aggregate(
        min_price_global=Min('price'), max_price_global=Max('price')
    )

    # Atributos para filtro (productos sin filtrar por atributo, con category/search/price)
    products_for_attrs = Product.objects.filter(available=True)
    if category_slug:
        products_for_attrs = products_for_attrs.filter(category__slug=category_slug)
    if search_query:
        products_for_attrs = products_for_attrs.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(keywords__icontains=search_query)
        )
    if min_price is not None and min_price > 0:
        products_for_attrs = products_for_attrs.filter(price__gte=min_price)
    if max_price is not None and max_price > 0:
        products_for_attrs = products_for_attrs.filter(price__lte=max_price)

    attr_options = []
    if products_for_attrs.exists():
        attr_options = (
            ProductAttribute.objects.filter(product__in=products_for_attrs)
            .values('key', 'value')
            .annotate(count=Count('product', distinct=True))
            .order_by('key', 'value')
        )

    # Productos destacados (proxy "mejor valorados")
    top_products = Product.objects.filter(available=True).order_by('-created_at')[:3]

    context = {
        'products': page_obj,
        'categories': category_qs,
        'current_category': category_slug,
        'search_query': search_query,
        'min_price': min_price_param,
        'max_price': max_price_param,
        'attr_key': attr_key_param,
        'attr_value': attr_value_param,
        'attr_options': attr_options,
        'order': order,
        'price_range': price_range,
        'top_products': top_products,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'store/product_list_partial.html', context)
    return render(request, 'store/product_list.html', context)


def product_detail(request, slug):
    """Product detail page"""
    product = get_object_or_404(Product, slug=slug, available=True)
    
    # Get images ordered by primary first (primary images appear first)
    # This ensures that images with is_primary=True come first
    images = product.images.all().order_by('-is_primary', 'created_at')
    
    # Determine which image to show as primary
    # Priority: 1) product.image (main product image field), 2) ProductImage with is_primary=True, 3) First ProductImage
    primary_image = None
    
    # First priority: product.image field (same as home page)
    if product.image:
        primary_image = product.image
    
    # Second priority: ProductImage marked as primary (if product.image doesn't exist)
    if not primary_image and images.exists():
        primary_image_obj = images.filter(is_primary=True).first()
        if primary_image_obj:
            primary_image = primary_image_obj
        else:
            # Third priority: First ProductImage
            primary_image = images.first()
    
    # Get attributes
    attributes = product.attributes.all().order_by('order', 'key')
    
    # Get cart quantity for this product
    cart_quantity = 0
    if request.user.is_authenticated:
        try:
            cart_obj = Cart.objects.get(user=request.user)
            try:
                cart_item = cart_obj.items.get(product=product)
                cart_quantity = cart_item.quantity
            except CartItem.DoesNotExist:
                pass
        except Cart.DoesNotExist:
            pass
    else:
        session_cart = request.session.get('cart', {})
        cart_quantity = session_cart.get(str(product.id), 0)
    
    related_qs = product.related_products.filter(available=True)
    if related_qs.exists():
        related_products = related_qs[:8]
    else:
        related_products = Product.objects.filter(
            category=product.category,
            available=True
        ).exclude(id=product.id)[:8]

    # Favoritos (solo logueados)
    is_favorited = False
    if request.user.is_authenticated:
        try:
            from .models import FavoriteProduct
            is_favorited = FavoriteProduct.objects.filter(user=request.user, product=product).exists()
        except Exception:
            is_favorited = False
    
    # Debug: Print primary_image info
    # print(f"Primary image: {primary_image}")
    # print(f"Primary image type: {type(primary_image)}")
    # if primary_image:
    #     print(f"Has .image attr: {hasattr(primary_image, 'image')}")
    #     if hasattr(primary_image, 'image'):
    #         print(f"Primary image.image: {primary_image.image}")
    
    context = {
        'product': product,
        'images': images,
        'primary_image': primary_image,
        'attributes': attributes,
        'cart_quantity': cart_quantity,
        'related_products': related_products,
        'is_favorited': is_favorited,
    }
    return render(request, 'store/product_detail.html', context)


def cart(request):
    """Shopping cart page"""
    if request.user.is_authenticated:
        cart_obj, created = Cart.objects.get_or_create(user=request.user)
        cart_items = cart_obj.items.all()
        cart_total = cart_obj.total
        cart_item_count = cart_obj.item_count
    else:
        # Handle anonymous user cart from session
        from decimal import Decimal
        cart_items = []
        cart_total = Decimal('0.00')
        session_cart = request.session.get('cart', {})
        for product_id_str, quantity in session_cart.items():
            try:
                product = Product.objects.get(id=int(product_id_str), available=True)
                # Create a temporary cart item-like object
                class TempCartItem:
                    def __init__(self, product, quantity):
                        self.product = product
                        self.quantity = quantity
                        self.id = product.id
                    
                    @property
                    def subtotal(self):
                        return self.product.selling_price * self.quantity
                
                item = TempCartItem(product, quantity)
                cart_items.append(item)
                cart_total += item.subtotal
            except (Product.DoesNotExist, ValueError):
                continue
        cart_item_count = sum(session_cart.values()) if isinstance(session_cart, dict) else 0
    
    context = {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'store/cart.html', context)


def add_to_cart(request, product_id):
    """Add product to cart"""
    product = get_object_or_404(Product, id=product_id, available=True)
    quantity = int(request.POST.get('quantity', 1))
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # No permitir agregar si no hay stock o cantidad inválida
    if product.stock <= 0:
        error_message = 'Este producto no tiene stock disponible.'
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': error_message,
                'available_stock': 0,
            }, status=400)
        messages.error(request, error_message)
        return redirect('store:product_detail', slug=product.slug)
    if quantity < 1:
        quantity = 1
    # Validate stock
    if quantity > product.stock:
        error_message = f'No hay suficiente stock. Solo hay {product.stock} unidades disponibles.'
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': error_message,
                'available_stock': product.stock,
            }, status=400)
        messages.error(request, error_message)
        return redirect('store:product_detail', slug=product.slug)
    
    if request.user.is_authenticated:
        cart_obj, created = Cart.objects.get_or_create(user=request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart_obj,
            product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            # Check if adding more would exceed stock
            if cart_item.quantity + quantity > product.stock:
                error_message = f'No hay suficiente stock. Solo hay {product.stock} unidades disponibles.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': error_message,
                        'available_stock': product.stock,
                        'product_id': product.id,
                        'cart_quantity': cart_item.quantity,
                    }, status=400)
                messages.error(request, error_message)
                return redirect('store:product_detail', slug=product.slug)
            cart_item.quantity += quantity
            cart_item.save()
        
        cart_item_count = cart_obj.item_count
    else:
        # Handle anonymous user
        cart = request.session.get('cart', {})
        product_id_str = str(product_id)
        current_quantity = cart.get(product_id_str, 0)
        
        # Check if adding more would exceed stock
        if current_quantity + quantity > product.stock:
            error_message = f'No hay suficiente stock. Solo hay {product.stock} unidades disponibles.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': error_message,
                    'available_stock': product.stock,
                    'product_id': product.id,
                    'cart_quantity': current_quantity,
                }, status=400)
            messages.error(request, error_message)
            return redirect('store:product_detail', slug=product.slug)
        
        cart[product_id_str] = current_quantity + quantity
        request.session['cart'] = cart
        request.session.modified = True
        cart_item_count = sum(cart.values())
    
    if is_ajax:
        return JsonResponse({
            'success': True,
            'product_name': product.name,
            'cart_item_count': cart_item_count,
            'product_id': product.id,
            'product_stock': product.stock,
            'cart_quantity': cart.get(str(product_id), 0) if not request.user.is_authenticated else cart_item.quantity,
        })
    
    messages.success(request, f'{product.name} agregado al carrito')
    return redirect('store:cart')


def update_cart_item(request, item_id):
    """Update cart item quantity"""
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
        return redirect('store:cart')
    
    quantity = int(request.POST.get('quantity', 1))
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.user.is_authenticated:
        try:
            cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
            product = cart_item.product
            
            # Validate stock
            if quantity > product.stock:
                error_message = f'No hay suficiente stock. Solo hay {product.stock} unidades disponibles.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': error_message,
                        'available_stock': product.stock,
                        'product_id': product.id,
                        'product_stock': product.stock,
                    }, status=400)
                messages.error(request, error_message)
                return redirect('store:cart')
            
            if quantity > 0:
                cart_item.quantity = quantity
                cart_item.save()
                cart_obj = cart_item.cart
                item_subtotal = cart_item.subtotal
                final_quantity = quantity
            else:
                cart_obj = cart_item.cart
                item_subtotal = Decimal('0.00')
                final_quantity = 0
                product_id = product.id
                product_stock = product.stock
                cart_item.delete()
            
            cart_item_count = cart_obj.item_count
            cart_total = cart_obj.total
            product_id = product.id
            product_stock = product.stock
        except CartItem.DoesNotExist:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'Item no encontrado',
                }, status=404)
            messages.error(request, 'Item no encontrado')
            return redirect('store:cart')
    else:
        # Handle anonymous user
        cart = request.session.get('cart', {})
        product_id_str = str(item_id)  # In session, item_id is product_id
        
        # Get product to validate stock
        try:
            product = Product.objects.get(id=int(product_id_str), available=True)
            
            # Validate stock
            if quantity > product.stock:
                error_message = f'No hay suficiente stock. Solo hay {product.stock} unidades disponibles.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': error_message,
                        'available_stock': product.stock,
                        'product_id': product.id,
                        'product_stock': product.stock,
                    }, status=400)
                messages.error(request, error_message)
                return redirect('store:cart')
        except Product.DoesNotExist:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'Producto no encontrado',
                }, status=404)
            messages.error(request, 'Producto no encontrado')
            return redirect('store:cart')
        
        if quantity > 0:
            cart[product_id_str] = quantity
        else:
            cart.pop(product_id_str, None)
        
        request.session['cart'] = cart
        request.session.modified = True
        
        # Calculate cart count and total for anonymous users
        cart_item_count = sum(cart.values())
        cart_total = Decimal('0.00')
        item_subtotal = Decimal('0.00')
        
        for pid_str, qty in cart.items():
            try:
                p = Product.objects.get(id=int(pid_str), available=True)
                if pid_str == product_id_str:
                    item_subtotal = p.selling_price * qty
                cart_total += p.selling_price * qty
            except Product.DoesNotExist:
                continue
        
        product_id = product.id
        product_stock = product.stock
        final_quantity = quantity
    
    # Handle AJAX requests
    if is_ajax:
        return JsonResponse({
            'success': True,
            'cart_item_count': cart_item_count,
            'cart_total': str(cart_total),
            'item_subtotal': str(item_subtotal),
            'product_id': product_id,
            'product_stock': product_stock,
            'cart_quantity': final_quantity,
        })
    
    messages.success(request, 'Carrito actualizado')
    return redirect('store:cart')


def remove_from_cart(request, item_id):
    """Remove item from cart"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.user.is_authenticated:
        try:
            cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
            product_id = cart_item.product.id
            product_stock = cart_item.product.stock
            cart_item.delete()
            cart_obj = Cart.objects.get(user=request.user)
            cart_item_count = cart_obj.item_count
            cart_total = cart_obj.total
        except CartItem.DoesNotExist:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'Item no encontrado',
                }, status=404)
            messages.error(request, 'Item no encontrado')
            return redirect('store:cart')
    else:
        # Handle anonymous user
        cart = request.session.get('cart', {})
        product_id_str = str(item_id)  # In session, item_id is product_id
        
        try:
            product = Product.objects.get(id=int(product_id_str), available=True)
            product_id = product.id
            product_stock = product.stock
        except Product.DoesNotExist:
            product_id = None
            product_stock = 0
        
        cart.pop(product_id_str, None)
        request.session['cart'] = cart
        request.session.modified = True
        
        # Calculate cart count and total for anonymous users
        cart_item_count = sum(cart.values())
        cart_total = Decimal('0.00')
        for pid_str, qty in cart.items():
            try:
                p = Product.objects.get(id=int(pid_str), available=True)
                cart_total += p.selling_price * qty
            except Product.DoesNotExist:
                continue
    
    # Handle AJAX requests
    if is_ajax:
        return JsonResponse({
            'success': True,
            'cart_item_count': cart_item_count,
            'cart_total': str(cart_total),
            'product_id': product_id if product_id else None,
            'product_stock': product_stock if product_id else 0,
            'cart_quantity': 0,
        })
    
    messages.success(request, 'Item eliminado del carrito')
    return redirect('store:cart')


@login_required
def checkout(request):
    """Checkout page"""
    if not request.user.is_authenticated:
        messages.error(request, 'Debes iniciar sesión para realizar el checkout')
        return redirect('accounts:login')

    cart_obj, created = Cart.objects.get_or_create(user=request.user)
    cart_items = list(cart_obj.items.all())

    if not cart_items:
        messages.warning(request, 'Tu carrito está vacío')
        return redirect('store:cart')

    # Direcciones de envío guardadas
    default_address = None
    addresses = []
    if hasattr(request.user, 'shipping_addresses'):
        addresses = list(request.user.shipping_addresses.all())
        if hasattr(request.user, 'profile') and request.user.profile.default_shipping_address_id:
            default_address = request.user.profile.default_shipping_address

    # Si el usuario confirma el pedido, generar una cotización como en guest_checkout
    if request.method == 'POST':
        from decimal import Decimal

        # Si el usuario eligió una dirección guardada, tomamos los datos desde ahí
        saved_address_id = (request.POST.get('saved_address') or '').strip()
        departamento = city = address = ref = maps_url = phone = ''
        from_saved_address = False
        notes_extra = request.POST.get('shipping_notes', '').strip()

        if saved_address_id:
            from accounts.models import ShippingAddress
            try:
                addr_obj = ShippingAddress.objects.get(id=saved_address_id, user=request.user)
                departamento = addr_obj.departamento or ''
                city = addr_obj.city or ''
                address = addr_obj.address or ''
                ref = addr_obj.punto_referencia or ''
                maps_url = addr_obj.google_maps_ubicacion or ''
                phone = addr_obj.phone or ''
                from_saved_address = True
            except ShippingAddress.DoesNotExist:
                saved_address_id = ''

        # Si NO hay dirección guardada seleccionada, usamos lo que viene del formulario (nueva ubicación)
        if not saved_address_id:
            departamento = request.POST.get('shipping_departamento', '').strip()
            city = request.POST.get('shipping_city', '').strip()
            address = request.POST.get('shipping_address', '').strip()
            ref = request.POST.get('shipping_punto_referencia', '').strip()
            maps_url = request.POST.get('shipping_google_maps', '').strip()
            phone = request.POST.get('shipping_phone', '').strip()

        # Validaciones mínimas con detalle de qué falta
        missing = []
        # Si viene de una dirección guardada, asumimos que es válida
        if not from_saved_address:
            if not departamento:
                missing.append('Departamento')
            if not city:
                missing.append('Ciudad')
            if not address:
                missing.append('Dirección exacta')
            if not phone:
                missing.append('Teléfono')

        if missing:
            messages.error(
                request,
                'Por favor completa los siguientes campos obligatorios: ' + ', '.join(missing)
            )
        else:
            extra_notes_parts = [address]
            if ref:
                extra_notes_parts.append(f"Punto de referencia: {ref}")
            if maps_url:
                extra_notes_parts.append(f"Ubicación (mapa): {maps_url}")
            if notes_extra:
                extra_notes_parts.append(f"Notas adicionales: {notes_extra}")
            notes = " | ".join(extra_notes_parts)

            user = request.user
            full_name = user.get_full_name() or user.username
            email = user.email or ''
            profile = getattr(user, 'profile', None)
            kind = 'natural'
            if profile and (profile.client_type or '') in ('natural', 'empresa'):
                kind = profile.client_type
            if not phone and profile:
                phone = (profile.phone or '').strip()

            quotation_obj = Quotation.objects.create(
                created_by=user,
                existing_client=user,
                client_kind=kind,
                client_name=full_name,
                client_email=email,
                client_phone=phone,
                client_departamento=departamento,
                client_city=city,
                notes=notes,
                total=Decimal('0.00'),
            )

            running_total = Decimal('0.00')
            for item in cart_items:
                price = item.product.selling_price
                qitem = QuotationItem.objects.create(
                    quotation=quotation_obj,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=price,
                    subtotal=price * item.quantity,
                )
                running_total += qitem.subtotal

            quotation_obj.total = running_total
            quotation_obj.save(update_fields=['total', 'updated_at'])

            # Vaciar carrito del usuario
            cart_obj.items.all().delete()

            # Enviar aviso a Telegram como pedido de cliente registrado
            logger.info(
                "[CHECKOUT] Enviando notificación a Telegram para cotización %s (cliente registrado)",
                quotation_obj.id,
            )
            _notify_telegram_new_quotation(quotation_obj, is_registered=True)
            _notify_wa_new_quotation(quotation_obj, source='Checkout cliente registrado', request=request)

            # Mostrar la misma página de "pasarela deshabilitada" / pedido registrado
            return render(request, 'store/guest_checkout_success.html', {
                'quote': quotation_obj,
                'cart_items': cart_items,
            })

    from accounts.forms import DEPARTAMENTOS_COLOMBIA
    context = {
        'cart_items': cart_items,
        'cart_total': cart_obj.total,
        'default_address': default_address,
        'addresses': addresses,
        'departamentos': [c for c in DEPARTAMENTOS_COLOMBIA if c[0]],
    }
    return render(request, 'store/checkout.html', context)


def guest_checkout(request):
    """Checkout como invitado: usa carrito de sesión, no crea usuario, genera cotización."""
    if request.user.is_authenticated:
        # Usuarios logueados deben usar el checkout normal
        return redirect('store:checkout')

    from decimal import Decimal

    # Construir carrito desde sesión
    session_cart = request.session.get('cart', {})
    if not isinstance(session_cart, dict) or not session_cart:
        messages.warning(request, 'Tu carrito está vacío')
        return redirect('store:cart')

    cart_items = []
    cart_total = Decimal('0.00')
    ids = []
    for pid_str in session_cart.keys():
        try:
            ids.append(int(pid_str))
        except (TypeError, ValueError):
            continue
    products = Product.objects.filter(id__in=ids, available=True).in_bulk()

    class TempCartItem:
        def __init__(self, product, quantity):
            self.product = product
            self.quantity = quantity
            self.id = product.id

        @property
        def subtotal(self):
            return self.product.selling_price * self.quantity

    for pid_str, qty in session_cart.items():
        try:
            pid = int(pid_str)
            q = int(qty)
        except (TypeError, ValueError):
            continue
        product = products.get(pid)
        if not product or q <= 0:
            continue
        item = TempCartItem(product, q)
        cart_items.append(item)
        cart_total += item.subtotal

    if not cart_items:
        messages.warning(request, 'Tu carrito está vacío')
        return redirect('store:cart')

    if request.method == 'POST':
        form = GuestCheckoutForm(request.POST)
        if form.is_valid():
            # Crear cotización a partir del carrito de sesión
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            client_type = form.cleaned_data['client_type']
            departamento = form.cleaned_data['departamento']
            city = form.cleaned_data['city']
            address = form.cleaned_data['address']
            lat = form.cleaned_data.get('map_lat') or ''
            lng = form.cleaned_data.get('map_lng') or ''
            ref = form.cleaned_data.get('punto_referencia') or ''
            phone = form.cleaned_data['phone']

            extra_notes_parts = [address]
            if ref:
                extra_notes_parts.append(f"Punto de referencia: {ref}")
            if lat and lng:
                maps_url = f"https://www.google.com/maps?q={lat},{lng}"
                extra_notes_parts.append(f"Ubicación (mapa): {maps_url}")
            notes = " | ".join(extra_notes_parts)

            quotation_obj = Quotation.objects.create(
                created_by=None,
                existing_client=None,
                client_kind=client_type or 'natural',
                client_name=full_name,
                client_email=email,
                client_phone=phone,
                client_departamento=departamento,
                client_city=city,
                notes=notes,
                total=Decimal('0.00'),
            )

            running_total = Decimal('0.00')
            for item in cart_items:
                price = item.product.selling_price
                qitem = QuotationItem.objects.create(
                    quotation=quotation_obj,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=price,
                    subtotal=price * item.quantity,
                )
                running_total += qitem.subtotal

            quotation_obj.total = running_total
            quotation_obj.save(update_fields=['total', 'updated_at'])

            # Limpiar carrito de sesión
            request.session['cart'] = {}
            request.session.modified = True

            # Enviar aviso a Telegram (si está configurado)
            logger.info(
                "[GUEST_CHECKOUT] Enviando notificación a Telegram para cotización %s (cliente invitado)",
                quotation_obj.id,
            )
            _notify_telegram_new_quotation(quotation_obj, is_registered=False)
            _notify_wa_new_quotation(quotation_obj, source='Checkout invitado / cliente', request=request)

            return render(request, 'store/guest_checkout_success.html', {
                'quote': quotation_obj,
                'cart_items': cart_items,
            })
    else:
        form = GuestCheckoutForm()

    return render(request, 'store/guest_checkout.html', {
        'form': form,
        'cart_items': cart_items,
        'cart_total': cart_total,
    })


def guest_checkout_login(request):
    """
    Login desde la pestaña 'Ya he comprado / Tengo cuenta' en guest_checkout.
    - Autentica al usuario.
    - Pasa el carrito de sesión al carrito del usuario.
    - Redirige a /checkout/ para continuar el flujo normal.
    """
    if request.method != 'POST':
        return redirect('store:guest_checkout')

    username = (request.POST.get('username') or '').strip()
    password = (request.POST.get('password') or '').strip()

    # Guardamos el carrito de sesión ANTES de hacer login
    session_cart = request.session.get('cart', {}) or {}

    user = authenticate(request, username=username, password=password)
    if not user:
        messages.error(request, 'Usuario o contraseña incorrectos.')
        return redirect('store:guest_checkout')

    # Asociar carrito de sesión al carrito del usuario
    if isinstance(session_cart, dict) and session_cart:
        cart_obj, _ = Cart.objects.get_or_create(user=user)
        # Cargar productos válidos
        ids = []
        for pid_str in session_cart.keys():
            try:
                ids.append(int(pid_str))
            except (TypeError, ValueError):
                continue
        products = Product.objects.filter(id__in=ids, available=True).in_bulk()

        for pid_str, qty in session_cart.items():
            try:
                pid = int(pid_str)
                q = int(qty)
            except (TypeError, ValueError):
                continue
            if q <= 0:
                continue
            product = products.get(pid)
            if not product:
                continue
            item, created = CartItem.objects.get_or_create(
                cart=cart_obj,
                product=product,
                defaults={'quantity': q},
            )
            if not created:
                item.quantity += q
                item.save()

    # Hacemos login (rota la sesión pero ya tenemos el carrito en DB)
    auth_login(request, user)

    # Limpiamos carrito de sesión (opcional)
    request.session['cart'] = {}
    request.session.modified = True

    return redirect('store:checkout')


@login_required
def order_list(request):
    """Mis pedidos: compras (Orders), cotizaciones (Quotations), más comprados y favoritos."""
    from .models import FavoriteProduct

    # Solo pedidos ya pagados (el usuario ve estado: Pagado, En preparación, Enviado, Entregado)
    orders = (
        Order.objects
        .filter(user=request.user, status__in=['paid', 'preparing', 'shipped', 'delivered'])
        .prefetch_related('items__product')
        .order_by('-created_at')
    )

    quotations = (
        Quotation.objects
        .filter(existing_client=request.user)
        .prefetch_related('items__product')
        .order_by('-created_at')
    )

    favorites = (
        FavoriteProduct.objects
        .filter(user=request.user)
        .select_related('product', 'product__category')
        .order_by('-created_at')
    )

    # Top productos más comprados por este usuario
    top_products = []
    top = (
        OrderItem.objects
        .filter(order__user=request.user)
        .values('product_id')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:8]
    )
    top_ids = [row['product_id'] for row in top]
    products_by_id = Product.objects.filter(id__in=top_ids, available=True).in_bulk()
    for row in top:
        p = products_by_id.get(row['product_id'])
        if not p:
            continue
        top_products.append({'product': p, 'qty': row['total_qty']})

    context = {
        'orders': orders,
        'quotations': quotations,
        'favorites': favorites,
        'top_products': top_products,
    }
    return render(request, 'store/order_list.html', context)


@login_required
def favorite_toggle(request, product_id: int):
    """Guardar / quitar producto de favoritos (solo usuarios logueados)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    from .models import FavoriteProduct
    product = get_object_or_404(Product, id=product_id, available=True)

    obj = FavoriteProduct.objects.filter(user=request.user, product=product).first()
    if obj:
        obj.delete()
        return JsonResponse({'ok': True, 'favorited': False})
    FavoriteProduct.objects.create(user=request.user, product=product)
    return JsonResponse({'ok': True, 'favorited': True})


@login_required
def order_detail(request, order_id):
    """Order detail page"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    context = {
        'order': order,
    }
    return render(request, 'store/order_detail.html', context)


def about(request):
    """About page"""
    return render(request, 'store/about.html')


def privacy_policy(request):
    """Privacy policy page"""
    return render(request, 'store/privacy_policy.html')


def normatividad(request):
    """Normatividad page"""
    return render(request, 'store/normatividad.html')


# Manager - Clientes (staff only)
@staff_member_required
def client_list(request):
    """List all clients (non-staff users) with filters by search, type, email and phone."""
    from accounts.models import UserProfile
    clients = User.objects.filter(is_staff=False).select_related('profile').order_by('-date_joined')
    # Filtro por búsqueda (usuario, nombre, apellido)
    search = (request.GET.get('q') or '').strip()
    if search:
        clients = clients.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    # Filtro por correo
    filter_correo = (request.GET.get('correo') or '').strip()
    if filter_correo:
        clients = clients.filter(email__icontains=filter_correo)
    # Filtro por teléfono (perfil)
    filter_telefono = (request.GET.get('telefono') or '').strip()
    if filter_telefono:
        clients = clients.filter(profile__phone__icontains=filter_telefono)
    # Filtro por tipo de cliente (perfil)
    client_type = request.GET.get('tipo')
    if client_type and client_type in dict(UserProfile.CLIENT_TYPE_CHOICES):
        clients = clients.filter(profile__client_type=client_type)
    paginator = Paginator(clients, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj,
        'filter_q': search,
        'filter_correo': filter_correo,
        'filter_telefono': filter_telefono,
        'filter_tipo': client_type,
        'client_type_choices': UserProfile.CLIENT_TYPE_CHOICES,
    }
    return render(request, 'store/manager/client_list.html', context)


@staff_member_required
def client_create(request):
    """Create a new client (user with is_staff=False) with teléfono, tipo de cliente y dirección."""
    from store.forms import ClientCreateForm
    if request.method == 'POST':
        form = ClientCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = False
            user.save()
            # ClientCreateForm.save() already updates profile when commit=True; we saved user manually
            if hasattr(user, 'profile'):
                user.profile.phone = form.cleaned_data.get('phone', '')
                user.profile.client_type = form.cleaned_data.get('client_type', 'natural')
                user.profile.departamento = form.cleaned_data.get('departamento', '')
                user.profile.city = form.cleaned_data.get('city', '')
                user.profile.address = form.cleaned_data.get('address', '')
                user.profile.save()
            messages.success(request, f'Cliente "{user.get_full_name() or user.username}" creado correctamente.')
            # Guardar contraseña en sesión para mostrarla una sola vez en la página de detalle
            request.session['new_client_password'] = form.cleaned_data.get('password1', '')
            return redirect('store:client_detail', client_id=user.id)
    else:
        form = ClientCreateForm()
    for field in form.fields.values():
        current = field.widget.attrs.get('class', '')
        if 'form-control' not in current and 'form-select' not in current:
            field.widget.attrs['class'] = f'{current} form-control'.strip()
    context = {'form': form}
    return render(request, 'store/manager/client_form.html', context)


@staff_member_required
def client_detail(request, client_id):
    """View client details. Pass new_password if just created (from session, shown once)."""
    from .models import Quotation
    from decimal import Decimal
    client = get_object_or_404(User, id=client_id, is_staff=False)
    new_password = request.session.pop('new_client_password', None)
    # Cotizaciones del cliente (como existing_client)
    quotations = Quotation.objects.filter(existing_client=client).order_by('-created_at')
    quotations_active = quotations.exclude(quotation_status__in=['vencida', 'cancelada'])
    total_quotations = quotations.count()
    active_count = quotations_active.count()
    total_quoted = quotations.aggregate(s=Sum('total'))['s'] or Decimal('0')
    # Pedidos del cliente
    orders = client.orders.all().order_by('-created_at')
    total_orders = orders.count()
    total_ordered = orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
    context = {
        'client': client,
        'new_password': new_password,
        'quotations_active': quotations_active[:10],
        'quotations': quotations,
        'total_quotations': total_quotations,
        'active_quotations_count': active_count,
        'total_quoted': total_quoted,
        'orders': orders[:10],
        'total_orders': total_orders,
        'total_ordered': total_ordered,
    }
    return render(request, 'store/manager/client_detail.html', context)


@staff_member_required
def client_edit(request, client_id):
    """Edit a client"""
    from store.forms import ClientEditForm
    client = get_object_or_404(User, id=client_id, is_staff=False)
    if request.method == 'POST':
        form = ClientEditForm(request.POST)
        if form.is_valid():
            client.email = form.cleaned_data['email']
            client.first_name = form.cleaned_data['first_name']
            client.last_name = form.cleaned_data['last_name']
            client.save()
            if hasattr(client, 'profile'):
                client.profile.phone = form.cleaned_data.get('phone', '')
                client.profile.client_type = form.cleaned_data.get('client_type', 'natural')
                client.profile.departamento = form.cleaned_data.get('departamento', '')
                client.profile.city = form.cleaned_data.get('city', '')
                client.profile.address = form.cleaned_data.get('address', '')
                client.profile.save()

            # Actualizar cotizaciones vinculadas con el nombre/datos actuales
            linked_quotes = Quotation.objects.filter(existing_client=client)
            updated_quotes = 0
            for quote in linked_quotes.iterator():
                if quote.sync_client_snapshot_from_profile(save=True):
                    updated_quotes += 1

            msg = f'Cliente "{client.get_full_name() or client.username}" actualizado.'
            if updated_quotes:
                msg += f' Se sincronizaron {updated_quotes} cotización(es).'
            messages.success(request, msg)
            return redirect('store:client_detail', client_id=client.id)
    else:
        profile = getattr(client, 'profile', None)
        phone = (getattr(profile, 'phone', None) or '').replace('+57 ', '').replace('+57', '').strip() if profile else ''
        form = ClientEditForm(initial={
            'email': client.email,
            'first_name': client.first_name,
            'last_name': client.last_name,
            'phone': phone or '',
            'client_type': getattr(profile, 'client_type', 'natural') if profile else 'natural',
            'departamento': getattr(profile, 'departamento', '') or '' if profile else '',
            'city': getattr(profile, 'city', '') or '' if profile else '',
            'address': getattr(profile, 'address', '') or '' if profile else '',
        })
    context = {'form': form, 'client': client}
    return render(request, 'store/manager/client_edit.html', context)


@staff_member_required
def client_delete(request, client_id):
    """Delete a client (with confirmation)"""
    client = get_object_or_404(User, id=client_id, is_staff=False)
    if request.method == 'POST':
        name = client.get_full_name() or client.username
        client.delete()
        messages.success(request, f'Cliente "{name}" eliminado.')
        return redirect('store:client_list')
    return render(request, 'store/manager/client_confirm_delete.html', {'client': client})


@staff_member_required
def client_generate_password(request, client_id):
    """Generate a new random password for the client. POST only. Returns JSON."""
    import random
    import string
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    client = get_object_or_404(User, id=client_id, is_staff=False)
    chars = string.ascii_letters + string.digits
    chars = chars.replace('o', '').replace('O', '').replace('0', '').replace('l', '').replace('I', '')
    pwd = ''.join(random.choice(chars) for _ in range(12))
    client.set_password(pwd)
    client.save()
    return JsonResponse({'password': pwd})


def _staff_role_label(user: User) -> str:
    if user.is_superuser:
        return 'Administrador'
    if user.is_staff:
        return 'Vendedor'
    return 'Cliente'


@staff_member_required
def staff_user_list(request):
    """Listado de personal (vendedores / admins) + edición de nombre de empresa."""
    from .forms import CompanyNameForm

    settings_obj = SiteSettings.load()
    company_form = CompanyNameForm(initial={'company_legal_name': settings_obj.company_legal_name})

    if request.method == 'POST' and request.POST.get('action') == 'update_company':
        company_form = CompanyNameForm(request.POST)
        if company_form.is_valid():
            settings_obj.company_legal_name = company_form.cleaned_data['company_legal_name'].strip()
            settings_obj.save(update_fields=['company_legal_name', 'updated_at'])
            messages.success(request, 'Nombre de la empresa actualizado.')
            return redirect('store:staff_user_list')

    q = (request.GET.get('q') or '').strip()
    role = (request.GET.get('role') or '').strip()
    users = User.objects.filter(is_staff=True).select_related('profile').order_by('-is_superuser', 'first_name', 'username')
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    if role == 'admin':
        users = users.filter(is_superuser=True)
    elif role == 'vendedor':
        users = users.filter(is_superuser=False)

    return render(request, 'store/manager/staff_user_list.html', {
        'users': users,
        'filter_q': q,
        'filter_role': role,
        'company_form': company_form,
        'settings_obj': settings_obj,
        'can_manage_admins': request.user.is_superuser,
    })


@staff_member_required
def staff_user_create(request):
    """Crear vendedor o administrador."""
    from .forms import StaffUserCreateForm

    allow_admin = request.user.is_superuser
    if request.method == 'POST':
        form = StaffUserCreateForm(request.POST, request.FILES, allow_admin_role=allow_admin)
        if form.is_valid():
            user = form.save()
            role = 'Administrador' if user.is_superuser else 'Vendedor'
            messages.success(request, f'{role} “{user.get_full_name() or user.username}” creado correctamente.')
            request.session['new_staff_password'] = form.cleaned_data.get('password1', '')
            return redirect('store:staff_user_edit', user_id=user.id)
    else:
        form = StaffUserCreateForm(allow_admin_role=allow_admin)

    return render(request, 'store/manager/staff_user_form.html', {
        'form': form,
        'title': 'Nuevo usuario del equipo',
        'is_create': True,
        'can_manage_admins': allow_admin,
    })


@staff_member_required
def staff_user_edit(request, user_id):
    """Editar datos, rol y foto de perfil de un usuario staff."""
    from .forms import StaffUserEditForm

    target = get_object_or_404(User.objects.select_related('profile'), id=user_id, is_staff=True)
    allow_admin = request.user.is_superuser

    # Un vendedor no puede editar administradores ni a sí mismo promoverse
    if target.is_superuser and not allow_admin:
        messages.error(request, 'No tienes permiso para editar administradores.')
        return redirect('store:staff_user_list')

    profile = getattr(target, 'profile', None)
    new_password = request.session.pop('new_staff_password', None)

    if request.method == 'POST':
        form = StaffUserEditForm(request.POST, request.FILES, allow_admin_role=allow_admin)
        if form.is_valid():
            # Evitar que un admin se quite a sí mismo el rol admin y se bloquee
            new_role = form.cleaned_data['role']
            if target.id == request.user.id and new_role != 'admin' and target.is_superuser:
                messages.error(request, 'No puedes quitarte el rol de administrador a ti mismo.')
                return redirect('store:staff_user_edit', user_id=target.id)

            target.email = form.cleaned_data['email']
            target.first_name = form.cleaned_data['first_name']
            target.last_name = form.cleaned_data['last_name'] or ''
            target.is_staff = True
            if allow_admin:
                target.is_superuser = (new_role == 'admin')
            # No permitir desactivar la propia cuenta
            if target.id == request.user.id:
                target.is_active = True
            else:
                target.is_active = bool(form.cleaned_data.get('is_active'))

            new_pwd = (form.cleaned_data.get('new_password') or '').strip()
            if new_pwd:
                target.set_password(new_pwd)

            target.save()

            if profile is None:
                from accounts.models import UserProfile
                profile = UserProfile.objects.create(user=target)
            profile.phone = form.cleaned_data.get('phone', '') or ''
            if form.cleaned_data.get('clear_avatar') and profile.avatar:
                profile.avatar.delete(save=False)
                profile.avatar = None
            avatar = form.cleaned_data.get('avatar')
            if avatar:
                profile.avatar = avatar
            profile.save()

            messages.success(request, f'Usuario “{target.get_full_name() or target.username}” actualizado.')
            return redirect('store:staff_user_list')
    else:
        phone = ''
        if profile and profile.phone:
            phone = profile.phone.replace('+57 ', '').replace('+57', '').strip()
        form = StaffUserEditForm(
            initial={
                'email': target.email,
                'first_name': target.first_name,
                'last_name': target.last_name,
                'phone': phone,
                'role': 'admin' if target.is_superuser else 'vendedor',
                'is_active': target.is_active,
            },
            allow_admin_role=allow_admin,
        )

    return render(request, 'store/manager/staff_user_form.html', {
        'form': form,
        'title': f'Editar · {target.get_full_name() or target.username}',
        'is_create': False,
        'staff_user': target,
        'profile': profile,
        'new_password': new_password,
        'role_label': _staff_role_label(target),
        'can_manage_admins': allow_admin,
    })


@staff_member_required
def staff_user_toggle_active(request, user_id):
    """Activar/desactivar usuario staff (POST)."""
    if request.method != 'POST':
        return redirect('store:staff_user_list')
    target = get_object_or_404(User, id=user_id, is_staff=True)
    if target.id == request.user.id:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('store:staff_user_list')
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, 'No tienes permiso para modificar administradores.')
        return redirect('store:staff_user_list')
    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])
    estado = 'activado' if target.is_active else 'desactivado'
    messages.success(request, f'Usuario “{target.get_full_name() or target.username}” {estado}.')
    return redirect('store:staff_user_list')


# Inventory views (staff only)
@staff_member_required
def inventory_dashboard(request):
    """Inventory dashboard — secciones Venta y Alquiler."""
    # Cotizaciones ya aceptadas/pagadas que aún no restaron inventario
    _ensure_stock_deducted_for_committed_quotations()

    # Normalizar tipos legacy (insumo/desechable) a venta
    Product.objects.filter(product_type__in=('supply', 'disposable')).update(product_type='sale')

    sale_qs = Product.objects.exclude(product_type='rental')
    rental_qs = Product.objects.filter(product_type='rental')

    def _sale_stats(qs):
        total = qs.count()
        available = qs.filter(available=True).count()
        low_stock = qs.filter(stock__lt=5, stock__gt=0).count()
        out_of_stock = qs.filter(stock=0).count()
        sale_value = Decimal('0.00')
        cost_value = Decimal('0.00')
        margins = []
        for p in qs.only('price', 'promotional_price', 'purchase_cost', 'stock'):
            stock = int(p.stock or 0)
            if stock <= 0:
                continue
            sell = Decimal(str(p.selling_price or 0))
            cost = Decimal(str(p.purchase_cost or 0))
            sale_value += sell * stock
            cost_value += cost * stock
            if cost > 0:
                margins.append(((sell - cost) / cost) * Decimal('100'))
        profit = sale_value - cost_value
        margin_pct = (profit / cost_value * Decimal('100')) if cost_value > 0 else Decimal('0.00')
        avg_margin = (sum(margins) / Decimal(len(margins))) if margins else Decimal('0.00')
        return {
            'total': total,
            'available': available,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'sale_value': sale_value,
            'cost_value': cost_value,
            'profit': profit,
            'margin_pct': margin_pct,
            'avg_margin_pct': avg_margin,
        }

    def _rental_stats(qs):
        total = qs.count()
        available = qs.filter(available=True).count()
        unavailable = qs.filter(available=False).count()
        units = qs.aggregate(s=Sum('stock'))['s'] or 0
        commercial_value = Decimal('0.00')
        cost_value = Decimal('0.00')
        margins = []
        for p in qs.only('rental_commercial_value', 'purchase_cost', 'stock'):
            stock = int(p.stock or 0)
            # Equipos: si stock es 0 pero existe el registro, contar 1 unidad de activo
            units_count = stock if stock > 0 else 1
            commercial = Decimal(str(p.rental_commercial_value or 0))
            cost = Decimal(str(p.purchase_cost or 0))
            commercial_value += commercial * units_count
            cost_value += cost * units_count
            if cost > 0 and commercial > 0:
                margins.append(((commercial - cost) / cost) * Decimal('100'))
        difference = commercial_value - cost_value
        margin_pct = (
            (difference / cost_value * Decimal('100')) if cost_value > 0 else Decimal('0.00')
        )
        avg_margin = (sum(margins) / Decimal(len(margins))) if margins else Decimal('0.00')
        return {
            'total': total,
            'available': available,
            'unavailable': unavailable,
            'units': units,
            'commercial_value': commercial_value,
            'cost_value': cost_value,
            'difference': difference,
            'margin_pct': margin_pct,
            'avg_margin_pct': avg_margin,
        }

    sale_stats = _sale_stats(sale_qs)
    rental_stats = _rental_stats(rental_qs)

    sale_products = sale_qs.select_related('category').order_by('-created_at')
    rental_products = (
        rental_qs.select_related('category')
        .prefetch_related('rental_prices')
        .order_by('-created_at')
    )

    sale_page_obj = Paginator(sale_products, 15).get_page(request.GET.get('sale_page'))
    rental_page_obj = Paginator(rental_products, 15).get_page(request.GET.get('rental_page'))

    context = {
        'sale_stats': sale_stats,
        'rental_stats': rental_stats,
        'sale_page_obj': sale_page_obj,
        'rental_page_obj': rental_page_obj,
    }
    return render(request, 'store/inventory/dashboard.html', context)


@staff_member_required
def inventory_list(request):
    """List all products for inventory management"""
    products = Product.objects.select_related('category').prefetch_related('rental_prices').order_by('-created_at')
    
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'store/inventory/product_list.html', context)


@staff_member_required
def inventory_detail(request, product_id):
    """Product detail for inventory"""
    product = get_object_or_404(Product, id=product_id)
    images = product.images.all().order_by('-is_primary', 'created_at')
    variations = product.variations.all()
    technical_specs = product.technical_specs.all()
    attributes = product.attributes.all()
    
    context = {
        'product': product,
        'images': images,
        'variations': variations,
        'technical_specs': technical_specs,
        'attributes': attributes,
    }
    return render(request, 'store/inventory/product_detail.html', context)


@staff_member_required
def inventory_create(request):
    """Create a new product"""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            _process_rental_prices(request, product)
            
            # Process new attributes
            new_attr_index = 0
            while True:
                new_key = request.POST.get(f'new_attribute_key_{new_attr_index}', '').strip()
                new_value = request.POST.get(f'new_attribute_value_{new_attr_index}', '').strip()
                new_order = request.POST.get(f'new_attribute_order_{new_attr_index}', '0')
                
                if not new_key or not new_value:
                    break
                
                try:
                    order = int(new_order)
                except (ValueError, TypeError):
                    order = 0
                
                ProductAttribute.objects.create(
                    product=product,
                    key=new_key,
                    value=new_value,
                    order=order
                )
                new_attr_index += 1
            
            messages.success(request, f'Producto {product.name} creado exitosamente')
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductForm()
    
    context = {
        'form': form,
        'rental_period_choices': ProductRentalPrice.PERIOD_CHOICES,
    }
    return render(request, 'store/inventory/product_form.html', context)


RENTAL_PERIOD_ORDER = ('hourly', 'daily', 'weekly', 'monthly')


def _process_rental_prices(request, product):
    """Guardar tarifas de alquiler desde el formulario de inventario."""
    if product.product_type != 'rental':
        ProductRentalPrice.objects.filter(product=product).delete()
        return

    delete_ids = {int(x) for x in request.POST.getlist('delete_rental_price') if str(x).isdigit()}
    ProductRentalPrice.objects.filter(product=product, id__in=delete_ids).delete()

    for rental_price in ProductRentalPrice.objects.filter(product=product):
        price_key = f'rental_price_{rental_price.id}_price'
        if price_key not in request.POST:
            continue
        price_val = (request.POST.get(price_key) or '').strip()
        period_type = (request.POST.get(f'rental_price_{rental_price.id}_period') or rental_price.period_type).strip()
        if not price_val:
            rental_price.delete()
            continue
        try:
            rental_price.period_type = period_type
            rental_price.price = Decimal(price_val)
            rental_price.is_active = request.POST.get(f'rental_price_{rental_price.id}_active') == 'on'
            rental_price.order = int(request.POST.get(f'rental_price_{rental_price.id}_order', rental_price.order) or 0)
            rental_price.save()
        except (ValueError, TypeError):
            rental_price.delete()

    new_index = 0
    while True:
        period_type = (request.POST.get(f'new_rental_price_period_{new_index}') or '').strip()
        price_val = (request.POST.get(f'new_rental_price_price_{new_index}') or '').strip()
        if not period_type and not price_val:
            break
        if period_type and price_val:
            try:
                order = int(request.POST.get(f'new_rental_price_order_{new_index}', new_index) or new_index)
            except (ValueError, TypeError):
                order = new_index
            ProductRentalPrice.objects.update_or_create(
                product=product,
                period_type=period_type,
                defaults={
                    'price': Decimal(price_val),
                    'is_active': request.POST.get(f'new_rental_price_active_{new_index}') == 'on',
                    'order': order,
                },
            )
        new_index += 1

    product.sync_rental_catalog_price()


def _process_attributes(request, product):
    """Process attribute create/update/delete from POST data"""
    # Delete attributes marked for deletion
    for attr_id in request.POST.getlist('delete_attribute'):
        try:
            attr = ProductAttribute.objects.get(id=int(attr_id), product=product)
            attr.delete()
        except (ValueError, ProductAttribute.DoesNotExist):
            pass

    # Update existing attributes
    existing_attr_ids = set()
    for key in request.POST.keys():
        if key.startswith('attribute_') and key.endswith('_key'):
            attr_id = key.replace('attribute_', '').replace('_key', '')
            try:
                attr_id_int = int(attr_id)
                existing_attr_ids.add(attr_id_int)
                attr_key = request.POST.get(f'attribute_{attr_id}_key', '').strip()
                attr_value = request.POST.get(f'attribute_{attr_id}_value', '').strip()
                attr_order = request.POST.get(f'attribute_{attr_id}_order', '0')

                try:
                    attr = ProductAttribute.objects.get(id=attr_id_int, product=product)
                    if attr_key and attr_value:
                        attr.key = attr_key
                        attr.value = attr_value
                        try:
                            attr.order = int(attr_order)
                        except (ValueError, TypeError):
                            attr.order = 0
                        attr.save()
                    else:
                        attr.delete()
                except ProductAttribute.DoesNotExist:
                    pass
            except (ValueError, TypeError):
                pass

    # Create new attributes (use get_or_create to avoid unique_together violation)
    new_attr_index = 0
    created_ids = set()
    while True:
        new_key = request.POST.get(f'new_attribute_key_{new_attr_index}', '').strip()
        new_value = request.POST.get(f'new_attribute_value_{new_attr_index}', '').strip()
        new_order = request.POST.get(f'new_attribute_order_{new_attr_index}', '0')

        if not new_key or not new_value:
            break

        try:
            order = int(new_order)
        except (ValueError, TypeError):
            order = 0

        attr, created = ProductAttribute.objects.update_or_create(
            product=product,
            key=new_key,
            defaults={'value': new_value, 'order': order}
        )
        created_ids.add(attr.id)
        new_attr_index += 1

    # Delete attributes not in form (removed via JS) - but NOT newly created ones
    keep_ids = existing_attr_ids | created_ids
    for attr in ProductAttribute.objects.filter(product=product):
        if attr.id not in keep_ids:
            attr.delete()


@staff_member_required
def inventory_edit(request, product_id):
    """Edit a product - supports partial saves per section"""
    product = get_object_or_404(Product, id=product_id)
    save_section = request.POST.get('save_section') if request.method == 'POST' else None

    if request.method == 'POST':
        # Partial save: only process the requested section
        if save_section == 'basic':
            product.name = request.POST.get('name', product.name).strip()
            if request.POST.get('slug'):
                product.slug = request.POST.get('slug').strip()
            if request.POST.get('category'):
                product.category_id = request.POST.get('category')
            product.product_type = request.POST.get('product_type', product.product_type)
            product.description = request.POST.get('description', product.description)
            product.keywords = request.POST.get('keywords', product.keywords)
            if request.POST.get('accent_color_clear') == 'on':
                product.accent_color = ''
            else:
                color = (request.POST.get('accent_color') or '').strip()
                import re
                if color and re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
                    product.accent_color = color.upper()
                elif not color:
                    product.accent_color = ''
            product.unit_price_enabled = request.POST.get('unit_price_enabled') == 'on'
            unit_qty_raw = (request.POST.get('unit_quantity') or '').strip()
            unit_measure = (request.POST.get('unit_measure') or 'l').strip()
            valid_measures = {c[0] for c in Product.UNIT_MEASURE_CHOICES}
            if unit_measure not in valid_measures:
                unit_measure = 'l'
            product.unit_measure = unit_measure
            if product.unit_price_enabled and unit_qty_raw:
                try:
                    qty = Decimal(unit_qty_raw)
                    if qty > 0:
                        product.unit_quantity = qty
                    else:
                        product.unit_quantity = None
                        product.unit_price_enabled = False
                except Exception:
                    product.unit_quantity = None
                    product.unit_price_enabled = False
            else:
                product.unit_quantity = None
            product.save(update_fields=[
                'name', 'slug', 'category_id', 'product_type', 'description', 'keywords',
                'accent_color', 'unit_price_enabled', 'unit_quantity', 'unit_measure',
            ])
            messages.success(request, 'Información básica guardada')
            return redirect('store:inventory_edit', product_id=product.id)

        elif save_section == 'image':
            if request.FILES.get('image'):
                product.image = request.FILES['image']
                product.save(update_fields=['image'])
                messages.success(request, 'Imagen principal guardada')
            else:
                messages.info(request, 'Selecciona una imagen para guardar')
            return redirect('store:inventory_edit', product_id=product.id)

        elif save_section == 'pricing':
            try:
                if product.product_type == 'rental':
                    _process_rental_prices(request, product)
                    product.stock = int(request.POST.get('stock', product.stock) or 0)
                    product.available = request.POST.get('available') == 'on'
                    product.rental_brand = (request.POST.get('rental_brand') or '').strip()
                    product.rental_model = (request.POST.get('rental_model') or '').strip()
                    product.rental_serial = (request.POST.get('rental_serial') or '').strip()
                    product.rental_condition = (request.POST.get('rental_condition') or '').strip() or 'Buen estado de funcionamiento'
                    product.rental_accessories = (request.POST.get('rental_accessories') or '').strip()
                    cv = (request.POST.get('rental_commercial_value') or '').strip()
                    dep = (request.POST.get('rental_deposit') or '').strip()
                    try:
                        product.rental_commercial_value = Decimal(cv) if cv else None
                    except Exception:
                        product.rental_commercial_value = None
                    try:
                        product.rental_deposit = Decimal(dep) if dep else None
                    except Exception:
                        product.rental_deposit = None
                    product.save(update_fields=[
                        'stock', 'available',
                        'rental_brand', 'rental_model', 'rental_serial', 'rental_condition',
                        'rental_accessories', 'rental_commercial_value', 'rental_deposit',
                    ])
                    messages.success(request, 'Tarifas de alquiler, datos de contrato y disponibilidad guardados')
                else:
                    product.purchase_cost = Decimal(str(request.POST.get('purchase_cost', product.purchase_cost) or 0))
                    product.price = Decimal(str(request.POST.get('price', product.price) or 0))
                    pr = request.POST.get('promotional_price')
                    product.promotional_price = Decimal(pr) if pr else None
                    product.stock = int(request.POST.get('stock', product.stock) or 0)
                    product.available = request.POST.get('available') == 'on'
                    product.save(update_fields=['purchase_cost', 'price', 'promotional_price', 'stock', 'available'])
                    ProductRentalPrice.objects.filter(product=product).delete()
                    messages.success(request, 'Precio y stock guardados')
            except (ValueError, TypeError) as e:
                messages.error(request, f'Error en precio/stock: {e}')
            return redirect('store:inventory_edit', product_id=product.id)

        elif save_section == 'attributes':
            _process_attributes(request, product)
            messages.success(request, 'Atributos guardados')
            return redirect('store:inventory_edit', product_id=product.id)

        elif save_section == 'related':
            related_ids = request.POST.getlist('related_products')
            product.related_products.set(Product.objects.filter(id__in=[int(x) for x in related_ids if x]))
            messages.success(request, 'Productos relacionados guardados')
            return redirect('store:inventory_edit', product_id=product.id)

        # Full save (no save_section)
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save()
            _process_rental_prices(request, product)
            _process_attributes(request, product)
            messages.success(request, f'Producto {product.name} actualizado')
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductForm(instance=product)

    # Productos que se pueden elegir como relacionados (todos menos el actual)
    products_for_related = Product.objects.exclude(id=product.id).order_by('name')

    context = {
        'form': form,
        'product': product,
        'products_for_related': products_for_related,
        'rental_period_choices': ProductRentalPrice.PERIOD_CHOICES,
    }
    return render(request, 'store/inventory/product_form.html', context)


@staff_member_required
def inventory_delete(request, product_id):
    """Delete a product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Producto {product_name} eliminado exitosamente')
        return redirect('store:inventory_list')
    
    context = {
        'product': product,
    }
    return render(request, 'store/inventory/product_confirm_delete.html', context)


@staff_member_required
def inventory_duplicate(request, product_id):
    """Duplicate a product and redirect to edit the new one"""
    product = get_object_or_404(Product, id=product_id)
    base_name = f"{product.name} (Copia)"
    base_slug = slugify(base_name)
    slug = base_slug
    counter = 1
    while Product.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base_slug}-{counter}"

    new_product = Product.objects.create(
        name=base_name,
        slug=slug,
        description=product.description,
        category=product.category,
        product_type=product.product_type,
        price=product.price,
        promotional_price=product.promotional_price,
        purchase_cost=product.purchase_cost,
        stock=0,
        available=False,
        image=product.image,
        keywords=product.keywords,
        accent_color=product.accent_color,
        unit_price_enabled=product.unit_price_enabled,
        unit_quantity=product.unit_quantity,
        unit_measure=product.unit_measure,
    )

    for attr in product.attributes.all():
        ProductAttribute.objects.create(
            product=new_product,
            key=attr.key,
            value=attr.value,
            order=attr.order,
        )
    for rental_price in product.rental_prices.all():
        ProductRentalPrice.objects.create(
            product=new_product,
            period_type=rental_price.period_type,
            price=rental_price.price,
            is_active=rental_price.is_active,
            order=rental_price.order,
        )
    for spec in product.technical_specs.all():
        ProductTechnicalSpec.objects.create(
            product=new_product,
            name=spec.name,
            description=spec.description,
            order=spec.order,
        )
    for img in product.images.all():
        ProductImage.objects.create(
            product=new_product,
            image=img.image,
            alt_text=img.alt_text,
            is_primary=img.is_primary,
        )
    for var in product.variations.all():
        new_var = ProductVariation.objects.create(
            product=new_product,
            variation_type=var.variation_type,
            name=var.name,
            value=var.value,
            price_modifier=var.price_modifier,
            stock=0,
            available=var.available,
            sku='',
            image=var.image,
        )
        for vimg in var.images.all():
            ProductVariationImage.objects.create(
                variation=new_var,
                image=vimg.image,
                alt_text=vimg.alt_text,
                is_primary=vimg.is_primary,
            )
    new_product.related_products.set(product.related_products.all())

    messages.success(request, f'Producto duplicado como "{new_product.name}". Puedes modificarlo a continuación.')
    return redirect('store:inventory_edit', product_id=new_product.id)


@staff_member_required
def inventory_toggle_available(request, product_id):
    """Toggle product availability"""
    product = get_object_or_404(Product, id=product_id)
    product.available = not product.available
    product.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'available': product.available,
        })
    
    messages.success(request, f'Disponibilidad de {product.name} actualizada')
    page = request.GET.get('page')
    if request.GET.get('next') == 'dashboard':
        url = reverse('store:inventory_dashboard')
        params = []
        sale_page = request.GET.get('sale_page')
        rental_page = request.GET.get('rental_page')
        if sale_page and sale_page != '1':
            params.append(f'sale_page={sale_page}')
        if rental_page and rental_page != '1':
            params.append(f'rental_page={rental_page}')
        if params:
            url += '?' + '&'.join(params)
        return redirect(url)

    url = reverse('store:inventory_list')
    if page and page != '1':
        url += f'?page={page}'
    return redirect(url)


# Product images
@staff_member_required
def inventory_add_image(request, product_id):
    """Add image to product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.product = product
            image.save()
            messages.success(request, 'Imagen agregada exitosamente')
            if request.POST.get('next') == 'edit':
                return redirect('store:inventory_edit', product_id=product.id)
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductImageForm()
    
    context = {
        'form': form,
        'product': product,
    }
    return render(request, 'store/inventory/add_image.html', context)


@staff_member_required
def inventory_delete_image(request, product_id, image_id):
    """Delete product image"""
    image = get_object_or_404(ProductImage, id=image_id, product_id=product_id)
    
    if request.method == 'POST':
        image.delete()
        messages.success(request, 'Imagen eliminada exitosamente')
        if request.POST.get('next') == 'edit':
            return redirect('store:inventory_edit', product_id=product_id)
        return redirect('store:inventory_detail', product_id=product_id)
    
    context = {
        'image': image,
        'product': image.product,
    }
    return render(request, 'store/inventory/delete_image.html', context)


# Product variations
@staff_member_required
def inventory_add_variation(request, product_id):
    """Add variation to product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductVariationForm(request.POST, request.FILES)
        if form.is_valid():
            variation = form.save(commit=False)
            variation.product = product
            variation.save()
            messages.success(request, 'Variación agregada exitosamente')
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductVariationForm()
    
    context = {
        'form': form,
        'product': product,
    }
    return render(request, 'store/inventory/add_variation.html', context)


@staff_member_required
def inventory_edit_variation(request, product_id, variation_id):
    """Edit product variation"""
    variation = get_object_or_404(ProductVariation, id=variation_id, product_id=product_id)
    
    if request.method == 'POST':
        form = ProductVariationForm(request.POST, request.FILES, instance=variation)
        if form.is_valid():
            form.save()
            messages.success(request, 'Variación actualizada exitosamente')
            return redirect('store:inventory_detail', product_id=product_id)
    else:
        form = ProductVariationForm(instance=variation)
    
    context = {
        'form': form,
        'variation': variation,
        'product': variation.product,
    }
    return render(request, 'store/inventory/edit_variation.html', context)


@staff_member_required
def inventory_delete_variation(request, product_id, variation_id):
    """Delete product variation"""
    variation = get_object_or_404(ProductVariation, id=variation_id, product_id=product_id)
    
    if request.method == 'POST':
        variation.delete()
        messages.success(request, 'Variación eliminada exitosamente')
        return redirect('store:inventory_detail', product_id=product_id)
    
    context = {
        'variation': variation,
        'product': variation.product,
    }
    return render(request, 'store/inventory/delete_variation.html', context)


# Variation images
@staff_member_required
def inventory_add_variation_image(request, product_id, variation_id):
    """Add image to variation"""
    variation = get_object_or_404(ProductVariation, id=variation_id, product_id=product_id)
    
    if request.method == 'POST':
        form = ProductVariationImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.variation = variation
            image.save()
            messages.success(request, 'Imagen agregada exitosamente')
            return redirect('store:inventory_detail', product_id=product_id)
    else:
        form = ProductVariationImageForm()
    
    context = {
        'form': form,
        'variation': variation,
        'product': variation.product,
    }
    return render(request, 'store/inventory/add_variation_image.html', context)


@staff_member_required
def inventory_delete_variation_image(request, product_id, variation_id, image_id):
    """Delete variation image"""
    image = get_object_or_404(ProductVariationImage, id=image_id, variation_id=variation_id)
    
    if request.method == 'POST':
        image.delete()
        messages.success(request, 'Imagen eliminada exitosamente')
        return redirect('store:inventory_detail', product_id=product_id)
    
    context = {
        'image': image,
        'variation': image.variation,
        'product': image.variation.product,
    }
    return render(request, 'store/inventory/delete_variation_image.html', context)


# Technical specs
@staff_member_required
def inventory_add_technical_spec(request, product_id):
    """Add technical spec to product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductTechnicalSpecForm(request.POST)
        if form.is_valid():
            spec = form.save(commit=False)
            spec.product = product
            spec.save()
            messages.success(request, 'Especificación técnica agregada exitosamente')
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductTechnicalSpecForm()
    
    context = {
        'form': form,
        'product': product,
    }
    return render(request, 'store/inventory/add_technical_spec.html', context)


@staff_member_required
def inventory_edit_technical_spec(request, product_id, spec_id):
    """Edit technical spec"""
    spec = get_object_or_404(ProductTechnicalSpec, id=spec_id, product_id=product_id)
    
    if request.method == 'POST':
        form = ProductTechnicalSpecForm(request.POST, instance=spec)
        if form.is_valid():
            form.save()
            messages.success(request, 'Especificación técnica actualizada exitosamente')
            return redirect('store:inventory_detail', product_id=product_id)
    else:
        form = ProductTechnicalSpecForm(instance=spec)
    
    context = {
        'form': form,
        'spec': spec,
        'product': spec.product,
    }
    return render(request, 'store/inventory/edit_technical_spec.html', context)


@staff_member_required
def inventory_delete_technical_spec(request, product_id, spec_id):
    """Delete technical spec"""
    spec = get_object_or_404(ProductTechnicalSpec, id=spec_id, product_id=product_id)
    
    if request.method == 'POST':
        spec.delete()
        messages.success(request, 'Especificación técnica eliminada exitosamente')
        return redirect('store:inventory_detail', product_id=product_id)
    
    context = {
        'spec': spec,
        'product': spec.product,
    }
    return render(request, 'store/inventory/delete_technical_spec.html', context)


# Product attributes
@staff_member_required
def inventory_add_attribute(request, product_id):
    """Add attribute to product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductAttributeForm(request.POST)
        if form.is_valid():
            attribute = form.save(commit=False)
            attribute.product = product
            attribute.save()
            messages.success(request, 'Atributo agregado exitosamente')
            return redirect('store:inventory_detail', product_id=product.id)
    else:
        form = ProductAttributeForm()
    
    context = {
        'form': form,
        'product': product,
    }
    return render(request, 'store/inventory/add_attribute.html', context)


@staff_member_required
def inventory_edit_attribute(request, product_id, attribute_id):
    """Edit product attribute"""
    attribute = get_object_or_404(ProductAttribute, id=attribute_id, product_id=product_id)
    
    if request.method == 'POST':
        form = ProductAttributeForm(request.POST, instance=attribute)
        if form.is_valid():
            form.save()
            messages.success(request, 'Atributo actualizado exitosamente')
            return redirect('store:inventory_detail', product_id=product_id)
    else:
        form = ProductAttributeForm(instance=attribute)
    
    context = {
        'form': form,
        'attribute': attribute,
        'product': attribute.product,
    }
    return render(request, 'store/inventory/edit_attribute.html', context)


@staff_member_required
def inventory_delete_attribute(request, product_id, attribute_id):
    """Delete product attribute"""
    attribute = get_object_or_404(ProductAttribute, id=attribute_id, product_id=product_id)
    
    if request.method == 'POST':
        attribute.delete()
        messages.success(request, 'Atributo eliminado exitosamente')
        return redirect('store:inventory_detail', product_id=product_id)
    
    context = {
        'attribute': attribute,
        'product': attribute.product,
    }
    return render(request, 'store/inventory/delete_attribute.html', context)


# Categories
@staff_member_required
def inventory_create_category(request):
    """Create a new category"""
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Categoría {category.name} creada exitosamente')
            return JsonResponse({'success': True, 'category_id': category.id, 'category_name': category.name})
    else:
        form = CategoryForm()
    
    context = {
        'form': form,
    }
    return render(request, 'store/inventory/create_category_modal.html', context)


def quotation(request):
    """Vista de cotización - permite seleccionar productos y generar cotización"""
    # Iniciar cotización limpia (sale del modo edición)
    if request.method == 'GET' and request.GET.get('nueva') == '1':
        _clear_quotation_edit_session(request)
        return redirect('store:quotation')

    quotation_items = []
    total = Decimal('0.00')
    editing_quote = None
    editing_id = request.session.get('editing_quotation_id')
    if editing_id:
        try:
            editing_quote = Quotation.objects.filter(id=int(editing_id)).first()
        except (TypeError, ValueError):
            editing_quote = None
        if not editing_quote or not _quotation_can_edit(editing_quote):
            request.session.pop('editing_quotation_id', None)
            editing_quote = None
            editing_id = None
    
    # Si hay sesión de cotización, úsala como base (AJAX)
    session_quote = _get_quote_session(request)
    if session_quote:
        for line_key, entry in session_quote.items():
            try:
                product_id, rental_from_key = _parse_quote_line_key(line_key)
                # En edición permitir productos aunque ya no estén "available"
                product_qs = Product.objects.select_related('category')
                if editing_quote:
                    product = product_qs.get(id=product_id)
                else:
                    product = product_qs.get(id=product_id, available=True)
                entry = _normalize_quote_entry(entry)
                qty = entry['qty']
                rental_price_id = entry.get('rental_price_id') or rental_from_key
                list_unit = _quote_base_unit_price(product, rental_price_id=rental_price_id)
                price = _quote_unit_price(
                    product,
                    discount_value=entry.get('discount_value', entry.get('discount_percent', 0)),
                    discount_type=entry.get('discount_type', 'percent'),
                    rental_price_id=rental_price_id,
                )
                subtotal = price * qty
                total += subtotal
                period_label = ''
                display_name = product.name
                if rental_price_id:
                    tariff = ProductRentalPrice.objects.filter(
                        id=rental_price_id, product_id=product.id, is_active=True
                    ).first()
                    if tariff:
                        period_label = tariff.get_period_type_display()
                        display_name = f'{product.name} · {period_label}'
                quotation_items.append({
                    'product': product,
                    'line_key': line_key,
                    'display_name': display_name,
                    'period_label': period_label,
                    'quantity': qty,
                    'discount_type': entry.get('discount_type', 'percent'),
                    'discount_value': entry.get('discount_value', entry.get('discount_percent', 0)),
                    'discount_percent': entry.get('discount_percent', 0),
                    'rental_price_id': rental_price_id,
                    'list_unit_price': list_unit,
                    'unit_price': price,
                    'subtotal': subtotal,
                })
            except (Product.DoesNotExist, ValueError, TypeError):
                continue

    # Obtener productos seleccionados desde GET o POST (fallback/compat)
    if request.method == 'POST':
        form = QuotationForm(request.POST)
        # Para "Generar", la fuente de verdad es la sesión (AJAX).
        session_quote = _get_quote_session(request)
        product_ids = list(session_quote.keys())
        
        valid_client = True
        if form.is_valid() and product_ids:
            # Resolver cliente: existente o no registrado
            selected_client = form.cleaned_data.get('existing_client')
            unregistered = bool(form.cleaned_data.get('unregistered_client'))

            if selected_client and not unregistered:
                client_name = selected_client.get_full_name() or selected_client.username
                client_email = selected_client.email or ''
                client_phone = ''
                client_kind = 'natural'
                client_departamento = ''
                client_city = ''
                try:
                    profile = getattr(selected_client, 'profile', None)
                    if profile:
                        client_phone = (profile.phone or '').strip()
                        if (profile.client_type or '') in ('natural', 'empresa'):
                            client_kind = profile.client_type
                        client_departamento = (profile.departamento or '').strip()
                        client_city = (profile.city or '').strip()
                        if (not client_departamento or not client_city) and profile.default_shipping_address_id:
                            addr = profile.default_shipping_address
                            if addr:
                                client_departamento = client_departamento or (addr.departamento or '').strip()
                                client_city = client_city or (addr.city or '').strip()
                except Exception:
                    pass
            else:
                client_name = (form.cleaned_data.get('client_name') or '').strip()
                client_email = (form.cleaned_data.get('client_email') or '').strip()
                client_phone = (form.cleaned_data.get('client_phone') or '').strip()
                client_kind = (form.cleaned_data.get('client_kind') or '').strip()
                client_departamento = (form.cleaned_data.get('client_departamento') or '').strip()
                client_city = (form.cleaned_data.get('client_city') or '').strip()
                if not client_kind:
                    messages.error(request, 'Selecciona Persona natural o Empresa.')
                    valid_client = False
                if not client_name:
                    messages.error(request, 'Para cliente no registrado debes llenar el nombre.')
                    valid_client = False
                if not client_email:
                    messages.error(request, 'Para cliente no registrado el correo es obligatorio.')
                    valid_client = False
                if not client_phone:
                    messages.error(request, 'Para cliente no registrado el teléfono es obligatorio.')
                    valid_client = False
                if not client_departamento or not client_city:
                    messages.error(request, 'Para cliente no registrado selecciona Departamento y Ciudad.')
                    valid_client = False

        if form.is_valid() and product_ids and valid_client:
            is_update = bool(editing_quote and _quotation_can_edit(editing_quote))
            if is_update and editing_quote.stock_deducted:
                _restore_stock_for_quotation(editing_quote)

            if is_update:
                quotation_obj = editing_quote
                quotation_obj.existing_client = selected_client if (selected_client and not unregistered) else None
                quotation_obj.client_kind = client_kind or 'existing'
                quotation_obj.client_name = client_name or ''
                quotation_obj.client_email = client_email or ''
                quotation_obj.client_phone = client_phone or ''
                quotation_obj.client_departamento = client_departamento or ''
                quotation_obj.client_city = client_city or ''
                quotation_obj.notes = form.cleaned_data.get('notes', '') or ''
                quotation_obj.total = Decimal('0.00')
                quotation_obj.save()
                quotation_obj.items.all().delete()
            else:
                # Crear cotización en BD (registro)
                quotation_obj = Quotation.objects.create(
                    created_by=request.user if request.user.is_authenticated else None,
                    existing_client=selected_client if (selected_client and not unregistered) else None,
                    client_kind=client_kind or 'existing',
                    client_name=client_name or '',
                    client_email=client_email or '',
                    client_phone=client_phone or '',
                    client_departamento=client_departamento or '',
                    client_city=client_city or '',
                    notes=form.cleaned_data.get('notes', '') or '',
                    total=Decimal('0.00'),
                )

            running_total = Decimal('0.00')
            for line_key, entry in session_quote.items():
                try:
                    product_id, rental_from_key = _parse_quote_line_key(line_key)
                    if is_update:
                        product = Product.objects.get(id=product_id)
                    else:
                        product = Product.objects.get(id=product_id, available=True)
                except (Product.DoesNotExist, ValueError, TypeError):
                    continue
                entry = _normalize_quote_entry(entry)
                qty = entry['qty']
                rental_price_id = entry.get('rental_price_id') or rental_from_key
                list_unit = _quote_base_unit_price(product, rental_price_id=rental_price_id)
                price = _quote_unit_price(
                    product,
                    discount_value=entry.get('discount_value', entry.get('discount_percent', 0)),
                    discount_type=entry.get('discount_type', 'percent'),
                    rental_price_id=rental_price_id,
                )
                rental_obj = None
                if rental_price_id:
                    rental_obj = ProductRentalPrice.objects.filter(
                        id=rental_price_id, product_id=product.id
                    ).first()
                item = QuotationItem.objects.create(
                    quotation=quotation_obj,
                    product=product,
                    quantity=qty,
                    unit_price=price,
                    list_unit_price=list_unit,
                    rental_price=rental_obj,
                    subtotal=price * qty,
                )
                running_total += item.subtotal

            quotation_obj.total = running_total
            quotation_obj.save(update_fields=['total', 'updated_at'])

            if is_update and quotation_obj.order_status in _stock_commit_statuses():
                _deduct_stock_for_quotation(quotation_obj)

            # Limpiar sesión de cotización / edición
            _clear_quotation_edit_session(request)

            if is_update:
                messages.success(request, f'Cotización #{quotation_obj.id} actualizada correctamente.')
            else:
                _notify_wa_new_quotation(
                    quotation_obj,
                    source=f'Staff · {(request.user.get_full_name() or request.user.username) if request.user.is_authenticated else "Manager"}',
                    request=request,
                )
                messages.success(request, f'Cotización #{quotation_obj.id} generada exitosamente.')
            return redirect('store:quotation_detail', quotation_id=quotation_obj.id)
    else:
        initial = {}
        if editing_quote:
            has_existing = bool(editing_quote.existing_client_id)
            initial = {
                'existing_client': editing_quote.existing_client_id,
                'unregistered_client': not has_existing,
                'client_kind': editing_quote.client_kind if editing_quote.client_kind in ('natural', 'empresa') else 'natural',
                'client_name': editing_quote.client_name or '',
                'client_email': editing_quote.client_email or '',
                'client_phone': editing_quote.client_phone or '',
                'client_departamento': editing_quote.client_departamento or '',
                'client_city': editing_quote.client_city or '',
                'notes': editing_quote.notes or '',
            }
        form = QuotationForm(initial=initial)
        # Obtener productos desde GET (pueden venir desde la lista de productos)
        # Soporta "productId" o "productId:rentalPriceId"
        product_ids = request.GET.getlist('products')
        session_quote = _get_quote_session(request)

        seen = set()
        unique_line_keys = []
        for raw in product_ids:
            product_id, rental_price_id = _parse_quote_line_key(raw)
            if product_id is None:
                continue
            if rental_price_id:
                key = f'{product_id}:{rental_price_id}'
            else:
                # Producto alquiler sin tarifa: no agregar precio catálogo solo;
                # el usuario elige tarifas en el panel.
                try:
                    prod = Product.objects.only('id', 'product_type').get(id=product_id, available=True)
                    if prod.is_rental:
                        continue
                except Product.DoesNotExist:
                    continue
                key = str(product_id)
            if key not in seen:
                seen.add(key)
                unique_line_keys.append((key, product_id, rental_price_id))

        for key, product_id, rental_price_id in unique_line_keys:
            try:
                product = Product.objects.get(id=product_id, available=True)
                if rental_price_id and not ProductRentalPrice.objects.filter(
                    id=rental_price_id, product_id=product_id, is_active=True
                ).exists():
                    continue
                already = any(it.get('line_key') == key for it in quotation_items)
                if already or key in session_quote:
                    continue
                list_unit = _quote_base_unit_price(product, rental_price_id=rental_price_id)
                period_label = ''
                display_name = product.name
                if rental_price_id:
                    tariff = ProductRentalPrice.objects.filter(id=rental_price_id).first()
                    if tariff:
                        period_label = tariff.get_period_type_display()
                        display_name = f'{product.name} · {period_label}'
                quotation_items.append({
                    'product': product,
                    'line_key': key,
                    'display_name': display_name,
                    'period_label': period_label,
                    'quantity': 1,
                    'discount_type': 'percent',
                    'discount_value': 0.0,
                    'discount_percent': 0.0,
                    'rental_price_id': rental_price_id,
                    'list_unit_price': list_unit,
                    'unit_price': list_unit,
                    'subtotal': list_unit,
                })
                total += list_unit
                session_quote[key] = {
                    'qty': 1,
                    'discount_type': 'percent',
                    'discount_value': 0.0,
                    'discount_percent': 0.0,
                    'rental_price_id': rental_price_id,
                }
            except (Product.DoesNotExist, ValueError, TypeError):
                continue
        request.session['quotation'] = session_quote
        request.session.modified = True
 
    # Excluir solo productos NO alquiler ya agregados (alquiler permite varias tarifas)
    selected_product_ids = []
    selected_line_keys = set(session_quote.keys()) if session_quote else set()
    for item in quotation_items:
        pid = item['product'].id
        if item.get('rental_price_id'):
            continue
        selected_product_ids.append(pid)
    if selected_product_ids:
        all_products = (
            Product.objects.filter(available=True)
            .exclude(id__in=selected_product_ids)
            .select_related('category')
            .prefetch_related(
                Prefetch(
                    'rental_prices',
                    queryset=ProductRentalPrice.objects.filter(is_active=True).order_by('order', 'period_type'),
                )
            )
            .order_by('category__name', 'name')
        )
    else:
        all_products = (
            Product.objects.filter(available=True)
            .select_related('category')
            .prefetch_related(
                Prefetch(
                    'rental_prices',
                    queryset=ProductRentalPrice.objects.filter(is_active=True).order_by('order', 'period_type'),
                )
            )
            .order_by('category__name', 'name')
        )
    products_by_category = {}
    for product in all_products:
        category_name = product.category.name
        if category_name not in products_by_category:
            products_by_category[category_name] = []
        products_by_category[category_name].append(product)
    
    # Obtener todas las categorías para el selector
    categories = Category.objects.filter(products__available=True).distinct().order_by('name')
    
    clients = User.objects.filter(is_staff=False).order_by('first_name', 'last_name', 'username')
    context = {
        'form': form,
        'quotation_items': quotation_items,
        'selected_line_keys': selected_line_keys,
        'selected_line_keys_json': json.dumps(sorted(selected_line_keys)),
        'total': total,
        'all_products': all_products,
        'products_by_category': products_by_category,
        'categories': categories,
        'clients': clients,
        'editing_quote': editing_quote,
    }
    return render(request, 'store/quotation.html', context)


@staff_member_required
def quotation_edit(request, quotation_id):
    """Carga una cotización existente en el builder para modificarla."""
    quote = get_object_or_404(
        Quotation.objects.prefetch_related('items__product', 'items__rental_price'),
        id=quotation_id,
    )
    if not _quotation_can_edit(quote):
        messages.error(
            request,
            'Esta cotización no se puede modificar (cerrada, cancelada o ya pagada).',
        )
        return redirect('store:quotation_detail', quotation_id=quote.id)

    _load_quotation_into_session(request, quote)
    messages.info(
        request,
        f'Editando cotización #{quote.id}. Guarda los cambios cuando termines.',
    )
    return redirect('store:quotation')


@staff_member_required
def quotation_edit_cancel(request, quotation_id):
    """Cancela la edición en curso y vuelve al detalle."""
    editing_id = request.session.get('editing_quotation_id')
    try:
        editing_id = int(editing_id) if editing_id is not None else None
    except (TypeError, ValueError):
        editing_id = None
    if editing_id == quotation_id:
        _clear_quotation_edit_session(request)
    return redirect('store:quotation_detail', quotation_id=quotation_id)


@staff_member_required
def quotation_list(request):
    """Listado (registro) de cotizaciones realizadas con filtros por cliente, manager y estado."""
    quotes = Quotation.objects.select_related('existing_client', 'created_by').order_by('-created_at')
    # Marca cotizaciones con líneas de alquiler (para botón de contrato)
    from django.db.models import Exists, OuterRef
    rental_lines = QuotationItem.objects.filter(
        quotation_id=OuterRef('pk'),
        product__product_type='rental',
    )
    quotes = quotes.annotate(includes_rental=Exists(rental_lines))
    # Filtro por búsqueda de cliente (nombre o email)
    client_search = (request.GET.get('cliente') or '').strip()
    if client_search:
        quotes = quotes.filter(
            Q(client_name__icontains=client_search) | Q(client_email__icontains=client_search)
        )
    # Filtro por manager (creado por)
    manager_id = request.GET.get('manager')
    if manager_id:
        try:
            quotes = quotes.filter(created_by_id=int(manager_id))
        except ValueError:
            pass
    # Filtro por estado de cotización
    status_filter = request.GET.get('estado')
    if status_filter and status_filter in dict(Quotation.QUOTATION_STATUS_CHOICES):
        quotes = quotes.filter(quotation_status=status_filter)
    # Usuarios que han creado al menos una cotización (para el dropdown manager)
    manager_ids = Quotation.objects.exclude(created_by_id__isnull=True).values_list('created_by_id', flat=True).distinct()
    managers = User.objects.filter(id__in=manager_ids).order_by('username')
    return render(request, 'store/quotation_list.html', {
        'quotes': quotes,
        'managers': managers,
        'filter_cliente': client_search,
        'filter_manager': manager_id,
        'filter_estado': status_filter,
        'quotation_status_choices': Quotation.QUOTATION_STATUS_CHOICES,
        'order_status_choices': Quotation.ORDER_STATUS_CHOICES,
    })


@staff_member_required
def sales_list(request):
    """
    Vista de ventas con 3 tablas:
    - Cotizaciones pagadas
    - Cotizaciones por falta de pago (vencidas esperando pago)
    - Cotizaciones sin pagar (aceptadas / esperando pago vigentes)
    Cada una muestra las últimas 10 y un total (de todo el conjunto filtrado).
    """
    from django.utils import timezone

    base = Quotation.objects.select_related('existing_client', 'created_by').order_by('-created_at')

    client_search = (request.GET.get('cliente') or '').strip()
    manager_id = (request.GET.get('manager') or '').strip()
    date_from = (request.GET.get('desde') or '').strip()
    date_to = (request.GET.get('hasta') or '').strip()

    if client_search:
        base = base.filter(
            Q(client_name__icontains=client_search) | Q(client_email__icontains=client_search)
        )
    if manager_id:
        try:
            base = base.filter(created_by_id=int(manager_id))
        except ValueError:
            pass
    if date_from:
        try:
            base = base.filter(created_at__date__gte=date_from)
        except Exception:
            pass
    if date_to:
        try:
            base = base.filter(created_at__date__lte=date_to)
        except Exception:
            pass

    paid_statuses = ['pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado']

    now = timezone.now()
    expiry_cutoff = now - timedelta(days=1)

    paid_qs = base.filter(order_status__in=paid_statuses)
    # Por falta de pago: esperando pago y ya venció la vigencia (1 día)
    overdue_qs = base.filter(order_status='esperando_pago', created_at__lt=expiry_cutoff)
    # Sin pagar: aceptado, o esperando pago todavía vigente
    unpaid_qs = base.filter(
        Q(order_status='aceptado') |
        Q(order_status='esperando_pago', created_at__gte=expiry_cutoff)
    )

    def _section(qs):
        total = qs.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
        count = qs.count()
        items = list(qs[:10])
        return {
            'items': items,
            'total': total,
            'count': count,
            'showing': len(items),
        }

    manager_ids = Quotation.objects.exclude(created_by_id__isnull=True).values_list('created_by_id', flat=True).distinct()
    managers = User.objects.filter(id__in=manager_ids).order_by('username')

    return render(request, 'store/manager/sales_list.html', {
        'paid': _section(paid_qs),
        'overdue': _section(overdue_qs),
        'unpaid': _section(unpaid_qs),
        'managers': managers,
        'filter_cliente': client_search,
        'filter_manager': manager_id,
        'filter_desde': date_from,
        'filter_hasta': date_to,
    })


@staff_member_required
def finance_list(request):
    """Listado de gastos y pagos + formularios rápidos."""
    from .forms import FinanceRecordForm
    from datetime import date as date_cls

    records = FinanceRecord.objects.select_related(
        'created_by', 'related_quotation'
    ).order_by('-recorded_at', '-id')

    tipo = (request.GET.get('tipo') or '').strip()
    if tipo in dict(FinanceRecord.TYPE_CHOICES):
        records = records.filter(record_type=tipo)

    q = (request.GET.get('q') or '').strip()
    if q:
        records = records.filter(
            Q(description__icontains=q)
            | Q(notes__icontains=q)
            | Q(category__icontains=q)
        )

    form = FinanceRecordForm(initial={'recorded_at': date_cls.today(), 'record_type': 'gasto'})
    if request.method == 'POST':
        form = FinanceRecordForm(request.POST, request.FILES)
        if form.is_valid():
            record = form.save(commit=False)
            record.created_by = request.user
            record.save()
            _notify_wa_finance_record(record, request=request)
            messages.success(
                request,
                f'{record.get_record_type_display()} de ${record.amount} registrado y notificado a WhatsApp.',
            )
            return redirect('store:finance_list')

    gastos = FinanceRecord.objects.filter(record_type='gasto').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pagos = FinanceRecord.objects.filter(record_type='pago').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    paginator = Paginator(records, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'store/manager/finance_list.html', {
        'page_obj': page_obj,
        'form': form,
        'filter_tipo': tipo,
        'filter_q': q,
        'total_gastos': gastos,
        'total_pagos': pagos,
        'balance': pagos - gastos,
    })


@staff_member_required
def finance_delete(request, record_id):
    """Eliminar un gasto/pago."""
    record = get_object_or_404(FinanceRecord, id=record_id)
    if request.method == 'POST':
        label = f'{record.get_record_type_display()} ${record.amount}'
        record.delete()
        messages.success(request, f'{label} eliminado.')
        return redirect('store:finance_list')
    return render(request, 'store/manager/finance_confirm_delete.html', {'record': record})


@staff_member_required
def quotation_ajax_set_status(request):
    """AJAX: actualizar estado de cotización y/o estado del pedido inline (solo staff)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    qid = request.POST.get('quotation_id')
    qs = (request.POST.get('quotation_status') or '').strip()
    os_ = (request.POST.get('order_status') or '').strip()
    allowed_qs = {c[0] for c in getattr(Quotation, 'QUOTATION_STATUS_CHOICES', [])}
    allowed_os = {c[0] for c in getattr(Quotation, 'ORDER_STATUS_CHOICES', [])}
    try:
        qobj = Quotation.objects.get(id=int(qid))
    except Exception:
        return JsonResponse({'error': 'Invalid quotation_id'}, status=400)
    update_fields = []
    notify_pago = False
    if qs and qs in allowed_qs and qs != qobj.quotation_status:
        qobj.quotation_status = qs
        update_fields.extend(['quotation_status'])
    if os_ and os_ in allowed_os and os_ != qobj.order_status:
        # Estados que requieren comprobante de pago antes de avanzar
        post_payment_statuses = _post_payment_statuses()
        if os_ in post_payment_statuses and not qobj.payment_proof:
            return JsonResponse({
                'error': 'Debe subir una referencia de pago en el detalle de la cotización antes de marcar este estado.',
            }, status=400)
        # No permitir bajar de un estado post‑pago a uno previo
        if qobj.order_status in post_payment_statuses and os_ not in post_payment_statuses:
            return JsonResponse({
                'error': 'No es posible regresar el estado del pedido una vez que ha sido marcado como pagado/enviado/recibido.',
            }, status=400)
        # Descontar stock al aceptar (o al primer estado que compromete inventario)
        previous_status = qobj.order_status
        commit_statuses = _stock_commit_statuses()
        qobj.order_status = os_
        update_fields.extend(['order_status'])
        if os_ in commit_statuses and (
            previous_status not in commit_statuses or not qobj.stock_deducted
        ):
            _deduct_stock_for_quotation(qobj)
        notify_pago = (os_ == 'pago_recibido' and previous_status != 'pago_recibido')
        if os_ in _fully_paid_statuses() and _close_quotation_on_full_payment(qobj):
            update_fields.append('quotation_status')
    if update_fields:
        update_fields.append('updated_at')
        qobj.save(update_fields=list(dict.fromkeys(update_fields)))
    # Si ya estaba aceptada sin descontar (legado), sincronizar
    if qobj.order_status in _stock_commit_statuses() and not qobj.stock_deducted:
        _deduct_stock_for_quotation(qobj)
    if notify_pago:
        _notify_wa_quotation_payment(qobj, event='pago_recibido', request=request)
    return JsonResponse({
        'ok': True,
        'quotation_id': qobj.id,
        'quotation_status': qobj.quotation_status,
        'order_status': qobj.order_status,
    })


def quotation_detail(request, quotation_id):
    """Vista HTML final de una cotización"""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    items = q.items.select_related('product', 'product__category').all()
    expires_at = q.created_at + timedelta(days=1)

    # Subir referencia de pago (solo staff) — parcial o total actualiza el estado
    if request.method == 'POST' and request.user.is_authenticated and request.user.is_staff and request.FILES.get('payment_proof'):
        payment_type = (request.POST.get('payment_type') or 'total').strip().lower()
        if payment_type not in ('parcial', 'total'):
            payment_type = 'total'

        previous_status = q.order_status
        new_status = 'pago_parcial' if payment_type == 'parcial' else 'pago_recibido'
        quote_total = Decimal(str(q.total or 0))
        partial_amount = None

        if payment_type == 'parcial':
            raw_amount = (request.POST.get('partial_payment_amount') or '').strip().replace(',', '.')
            try:
                partial_amount = Decimal(raw_amount)
            except Exception:
                partial_amount = None
            if partial_amount is None or partial_amount <= 0:
                messages.error(request, 'Indica el valor del pago parcial (mayor a 0).')
                return redirect('store:quotation_detail', quotation_id=q.id)
            if quote_total > 0 and partial_amount >= quote_total:
                messages.error(
                    request,
                    f'El abono debe ser menor al total ({quote_total}). '
                    'Si ya pagó todo, elige pago Total.',
                )
                return redirect('store:quotation_detail', quotation_id=q.id)

        q.payment_proof = request.FILES['payment_proof']
        q.order_status = new_status
        update_fields = ['payment_proof', 'order_status', 'updated_at', 'partial_payment_amount']
        if payment_type == 'parcial':
            q.partial_payment_amount = partial_amount
        else:
            q.partial_payment_amount = None
            if _close_quotation_on_full_payment(q):
                update_fields.append('quotation_status')
        q.save(update_fields=update_fields)

        commit_statuses = _stock_commit_statuses()
        if new_status in commit_statuses and (
            previous_status not in commit_statuses or not q.stock_deducted
        ):
            _deduct_stock_for_quotation(q)

        if new_status == 'pago_recibido' and previous_status != 'pago_recibido':
            _notify_wa_quotation_payment(q, event='pago_recibido', request=request)
        else:
            _notify_wa_quotation_payment(
                q,
                event='pago_parcial' if payment_type == 'parcial' else 'referencia',
                request=request,
            )

        if payment_type == 'parcial':
            messages.success(
                request,
                f'Referencia de pago parcial subida por {_wa_money(partial_amount)}. '
                f'Saldo pendiente: {_wa_money(q.remaining_balance)}. '
                'Estado actualizado a «Pago parcial».',
            )
        else:
            messages.success(
                request,
                'Pago total registrado. Cotización cerrada como «Pagada». Ya puedes descargar la factura.',
            )
        return redirect('store:quotation_detail', quotation_id=q.id)

    # Actualizar estados (solo staff)
    if request.method == 'POST' and request.user.is_authenticated and request.user.is_staff:
        qs = (request.POST.get('quotation_status') or '').strip()
        os_ = (request.POST.get('order_status') or '').strip()
        allowed_qs = {c[0] for c in getattr(Quotation, 'QUOTATION_STATUS_CHOICES', [])}
        allowed_os = {c[0] for c in getattr(Quotation, 'ORDER_STATUS_CHOICES', [])}
        changed = False
        if qs and qs in allowed_qs and qs != q.quotation_status:
            q.quotation_status = qs
            changed = True
        if os_ and os_ in allowed_os and os_ != q.order_status:
            post_payment_statuses = _post_payment_statuses()
            if os_ in post_payment_statuses and not q.payment_proof:
                messages.warning(request, 'Debe subir una referencia de pago antes de marcar este estado de pedido.')
            else:
                if q.order_status in post_payment_statuses and os_ not in post_payment_statuses:
                    messages.warning(request, 'No es posible regresar el estado del pedido una vez que ha sido marcado como pagado/enviado/recibido.')
                else:
                    previous_status = q.order_status
                    commit_statuses = _stock_commit_statuses()
                    q.order_status = os_
                    changed = True
                    if os_ in commit_statuses and (
                        previous_status not in commit_statuses or not q.stock_deducted
                    ):
                        _deduct_stock_for_quotation(q)
                    if os_ == 'pago_recibido' and previous_status != 'pago_recibido':
                        _notify_wa_quotation_payment(q, event='pago_recibido', request=request)
                    if os_ in _fully_paid_statuses():
                        if _close_quotation_on_full_payment(q):
                            changed = True
        if changed:
            q.save(update_fields=['quotation_status', 'order_status', 'updated_at'])
            messages.success(request, 'Estados actualizados.')
        # Sincronizar stock si la cotización ya estaba aceptada sin descontar
        if q.order_status in _stock_commit_statuses() and not q.stock_deducted:
            _deduct_stock_for_quotation(q)
            messages.info(request, 'Inventario actualizado según productos aceptados.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    def split_iva(amount: Decimal):
        if amount is None:
            amount = Decimal('0.00')
        base = (amount / (Decimal('1.00') + IVA_RATE))
        iva = amount - base
        return base, iva

    total_base = Decimal('0.00')
    total_iva = Decimal('0.00')
    for it in items:
        it.base_unit, it.iva_unit = split_iva(it.unit_price)
        it.base_subtotal, it.iva_subtotal = split_iva(it.subtotal)
        # descuento si aplica (precio original - precio actual)
        try:
            it.original_unit_price = it.product.price
            it.discount_unit = (it.original_unit_price - it.unit_price) if it.product.has_discount else Decimal('0.00')
        except Exception:
            it.original_unit_price = it.unit_price
            it.discount_unit = Decimal('0.00')

        total_base += it.base_subtotal
        total_iva += it.iva_subtotal

    rental_requirements = None
    delivery_acta = None
    if q.has_rental_items:
        rental_requirements = RentalContractRequirements.objects.filter(quotation=q).first()
        delivery_acta = RentalDeliveryActa.objects.filter(quotation=q).first()

    # Completar tipo/depto/ciudad si la cotización se creó sin copiar el perfil
    q.sync_client_snapshot_from_profile(save=True)

    # Cotizaciones ya con pago total: asegurar cierre (legado)
    if q.order_status in _fully_paid_statuses() and q.quotation_status != 'cerrada':
        _close_quotation_on_full_payment(q)
        q.save(update_fields=['quotation_status', 'updated_at'])

    return render(
        request,
        'store/quotation_detail.html',
        {
            'quote': q,
            'items': items,
            'expires_at': expires_at,
            'total_base': total_base,
            'total_iva': total_iva,
            'rental_requirements': rental_requirements,
            'delivery_acta': delivery_acta,
            'is_fully_paid': _quotation_is_fully_paid(q) or q.order_status in _fully_paid_statuses(),
            'is_quote_closed': q.quotation_status == 'cerrada' or q.order_status in _fully_paid_statuses(),
            'can_edit_quote': _quotation_can_edit(q),
        },
    )


def _infer_quotation_list_unit_price(product, unit_price) -> Decimal:
    """Infer catalog/tariff list price for a saved quotation line (legacy items)."""
    unit = unit_price if unit_price is not None else Decimal('0.00')
    if getattr(product, 'is_rental', False) or getattr(product, 'product_type', '') == 'rental':
        tariffs = [
            rp.price
            for rp in product.rental_prices.filter(is_active=True)
            if rp.price is not None
        ]
        if tariffs:
            above = [t for t in tariffs if t >= unit]
            return min(above) if above else max(tariffs)
    catalog = getattr(product, 'price', None) or getattr(product, 'selling_price', None)
    if catalog is None:
        return unit
    return catalog if catalog >= unit else unit


def _normalize_pdf_iva_mode(raw) -> str:
    """Return 'with_iva' or 'no_iva' from request/query values."""
    value = str(raw or '').strip().lower()
    if value in ('0', 'false', 'no', 'sin', 'sin-iva', 'sin_iva', 'no_iva', 'no-iva'):
        return 'no_iva'
    return 'with_iva'


def _quotation_pdf_context(quote: Quotation, iva_mode: str = 'with_iva', doc_type: str = 'cotizacion') -> dict:
    """Shared context for quotation PDF HTML / xhtml2pdf."""
    quote.sync_client_snapshot_from_profile(save=True)
    show_iva = _normalize_pdf_iva_mode(iva_mode) == 'with_iva'
    is_factura = (doc_type or 'cotizacion') == 'factura'
    is_paid = _quotation_is_fully_paid(quote) or quote.order_status in _fully_paid_statuses()
    items = quote.items.select_related('product', 'product__category').prefetch_related(
        'product__rental_prices'
    ).all()
    expires_at = quote.created_at + timedelta(days=1)

    def split_iva(amount: Decimal):
        if amount is None:
            amount = Decimal('0.00')
        base = (amount / (Decimal('1.00') + IVA_RATE))
        iva = amount - base
        return base, iva

    total_base = Decimal('0.00')
    total_iva = Decimal('0.00')
    for it in items:
        it.base_unit, it.iva_unit = split_iva(it.unit_price)
        it.base_subtotal, it.iva_subtotal = split_iva(it.subtotal)
        try:
            list_price = it.list_unit_price
            if list_price is None:
                list_price = _infer_quotation_list_unit_price(it.product, it.unit_price)
            it.original_unit_price = list_price
            diff = list_price - it.unit_price
            it.discount_unit = diff if diff > 0 else Decimal('0.00')
        except Exception:
            it.original_unit_price = it.unit_price
            it.discount_unit = Decimal('0.00')
        total_base += it.base_subtotal
        total_iva += it.iva_subtotal

    return {
        'quote': quote,
        'items': items,
        'expires_at': expires_at,
        'total_base': total_base,
        'total_iva': total_iva,
        'show_iva': show_iva,
        'iva_mode': 'with_iva' if show_iva else 'no_iva',
        'payment_methods': PaymentMethod.objects.filter(is_active=True).order_by('sort_order', 'id'),
        'for_pdf_engine': True,
        'doc_type': 'factura' if is_factura else 'cotizacion',
        'is_factura': is_factura,
        'is_paid': is_paid,
        'show_paid_watermark': is_paid or is_factura,
    }


def _pdf_link_callback(uri, rel):
    """Resolve static/media URIs for xhtml2pdf (incluye URLs públicas de Supabase)."""
    from django.conf import settings
    from django.contrib.staticfiles import finders
    from urllib.parse import unquote, urlparse
    import tempfile

    raw = unquote(uri or '')
    parsed = urlparse(raw)

    # URL absoluta (Supabase Storage u otra CDN)
    if parsed.scheme in ('http', 'https'):
        try:
            import requests
            resp = requests.get(raw, timeout=20)
            resp.raise_for_status()
            suffix = os.path.splitext(parsed.path)[1] or '.bin'
            fd, tmp_path = tempfile.mkstemp(prefix='pdfimg_', suffix=suffix)
            with os.fdopen(fd, 'wb') as fh:
                fh.write(resp.content)
            return tmp_path
        except Exception:
            return uri

    path_only = parsed.path or raw

    if path_only.startswith(settings.MEDIA_URL):
        # Si media está en Supabase, reconstruir URL pública
        rel_name = path_only.replace(settings.MEDIA_URL, '', 1).lstrip('/')
        supabase_url = getattr(settings, 'SUPABASE_URL', '') or ''
        bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', '') or ''
        if supabase_url and bucket and getattr(settings, 'USE_SUPABASE_MEDIA', False):
            return _pdf_link_callback(
                f'{supabase_url.rstrip("/")}/storage/v1/object/public/{bucket}/{rel_name}',
                rel,
            )
        path = os.path.join(settings.MEDIA_ROOT, rel_name)
    elif path_only.startswith(settings.STATIC_URL):
        path = finders.find(path_only.replace(settings.STATIC_URL, '', 1))
    elif path_only.startswith('/static/'):
        path = finders.find(path_only.replace('/static/', '', 1))
    elif path_only.startswith('/media/'):
        path = os.path.join(settings.MEDIA_ROOT, path_only.replace('/media/', '', 1))
    else:
        path = path_only
    if not path:
        return uri
    if isinstance(path, (list, tuple)):
        path = path[0]
    return path


def _quotation_pdf_cache_path(quote: Quotation, iva_mode: str = 'with_iva', doc_type: str = 'cotizacion') -> str:
    """Disk cache path for generated quotation PDF (local media o /tmp en serverless)."""
    from django.conf import settings

    mode = _normalize_pdf_iva_mode(iva_mode)
    kind = 'fac' if doc_type == 'factura' else 'cot'
    paid = 'pagado' if _quotation_is_fully_paid(quote) or quote.order_status in _fully_paid_statuses() else 'abierto'
    stamp = quote.updated_at.strftime('%Y%m%d%H%M%S') if quote.updated_at else '0'
    folder = str(getattr(settings, 'PDF_CACHE_ROOT', None) or os.path.join(settings.MEDIA_ROOT, 'quotations', 'pdf_cache'))
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        # Último recurso en entornos read-only
        folder = os.path.join('/tmp', 'frozz_pdf_cache')
        os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f'COT{quote.id}-{stamp}-{mode}-{kind}-{paid}.pdf')


def _build_quotation_pdf_bytes(quote: Quotation, iva_mode: str = 'with_iva', doc_type: str = 'cotizacion'):
    """Generate PDF bytes with xhtml2pdf (cached by quote.updated_at + iva mode). Returns (bytes|None, error)."""
    mode = _normalize_pdf_iva_mode(iva_mode)
    kind = 'factura' if doc_type == 'factura' else 'cotizacion'
    cache_path = _quotation_pdf_cache_path(quote, mode, kind)
    try:
        if os.path.isfile(cache_path):
            with open(cache_path, 'rb') as fh:
                data = fh.read()
            if data.startswith(b'%PDF'):
                return data, None
    except OSError:
        pass

    try:
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO
    except ImportError:
        return None, 'xhtml2pdf no está instalado'

    template = get_template('store/quotation_pdf.html')
    html = template.render(_quotation_pdf_context(quote, iva_mode=mode, doc_type=kind))
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        return None, f'Error generando PDF: {pdf.err}'
    data = result.getvalue()
    try:
        # Limpia caches viejos de esta cotización (ambos modos)
        folder = os.path.dirname(cache_path)
        for name in os.listdir(folder):
            if name.startswith(f'COT{quote.id}-') and name.endswith('.pdf'):
                old = os.path.join(folder, name)
                if old != cache_path:
                    try:
                        os.remove(old)
                    except OSError:
                        pass
        with open(cache_path, 'wb') as fh:
            fh.write(data)
    except OSError:
        logger.exception('No se pudo cachear PDF de cotización %s', quote.id)
    return data, None


@xframe_options_sameorigin
def quotation_pdf(request, quotation_id):
    """Visor PDF de cotización (iframe) con descarga rápida."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    iva_mode = _normalize_pdf_iva_mode(request.GET.get('iva'))
    iva_qs = '1' if iva_mode == 'with_iva' else '0'
    doc_type = 'factura' if str(request.GET.get('tipo') or '').lower() in ('factura', 'invoice', 'fac') else 'cotizacion'
    safe_client = slugify(q.client_name or 'sin-cliente')[:40]
    mode_label = 'con-iva' if iva_mode == 'with_iva' else 'sin-iva'
    prefix = 'FAC' if doc_type == 'factura' else 'COT'
    filename = f"{prefix}{q.id}-{q.created_at.strftime('%Y-%m-%d')}-{safe_client}-{mode_label}.pdf"
    file_url = (
        reverse('store:quotation_pdf_file', kwargs={'quotation_id': q.id})
        + f'?iva={iva_qs}&tipo={"factura" if doc_type == "factura" else "cotizacion"}'
    )
    return render(request, 'store/quotation_pdf_viewer.html', {
        'quote': q,
        'filename': filename,
        'iva_mode': iva_mode,
        'show_iva': iva_mode == 'with_iva',
        'is_factura': doc_type == 'factura',
        'is_paid': _quotation_is_fully_paid(q) or q.order_status in _fully_paid_statuses(),
        'pdf_file_url': file_url,
        'pdf_download_url': file_url + '&download=1',
        'pdf_with_iva_url': reverse('store:quotation_pdf', kwargs={'quotation_id': q.id})
            + f'?iva=1&tipo={"factura" if doc_type == "factura" else "cotizacion"}',
        'pdf_no_iva_url': reverse('store:quotation_pdf', kwargs={'quotation_id': q.id})
            + f'?iva=0&tipo={"factura" if doc_type == "factura" else "cotizacion"}',
    })


@xframe_options_sameorigin
def quotation_pdf_file(request, quotation_id):
    """Sirve el PDF binario (inline para el visor, attachment para descargar)."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    iva_mode = _normalize_pdf_iva_mode(request.GET.get('iva'))
    iva_qs = '1' if iva_mode == 'with_iva' else '0'
    doc_type = 'factura' if str(request.GET.get('tipo') or '').lower() in ('factura', 'invoice', 'fac') else 'cotizacion'
    if doc_type == 'factura' and not (
        _quotation_is_fully_paid(q) or q.order_status in _fully_paid_statuses()
    ):
        return HttpResponse(
            'La factura solo está disponible cuando el pago es total.',
            content_type='text/plain; charset=utf-8',
            status=403,
        )
    pdf_bytes, err = _build_quotation_pdf_bytes(q, iva_mode=iva_mode, doc_type=doc_type)
    if not pdf_bytes:
        # Evitar HTML (con X-Frame-Options deny / redirects) dentro del iframe del visor.
        msg = err or 'No se pudo generar el PDF'
        return HttpResponse(
            f'<html><body style="font-family:sans-serif;padding:2rem;background:#111;color:#eee;">'
            f'<h3>No se pudo mostrar el PDF</h3><p>{msg}</p>'
            f'<p><a style="color:#93c5fd;" href="{reverse("store:quotation_pdf_file", kwargs={"quotation_id": q.id})}?iva={iva_qs}&tipo={doc_type}&download=1">'
            f'Descargar de nuevo</a></p></body></html>',
            content_type='text/html; charset=utf-8',
            status=500,
        )

    safe_client = slugify(q.client_name or 'sin-cliente')[:40]
    mode_label = 'con-iva' if iva_mode == 'with_iva' else 'sin-iva'
    prefix = 'FAC' if doc_type == 'factura' else 'COT'
    filename = f"{prefix}{q.id}-{q.created_at.strftime('%Y-%m-%d')}-{safe_client}-{mode_label}.pdf"
    as_download = str(request.GET.get('download') or '') in ('1', 'true', 'yes')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'attachment' if as_download else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    response['Cache-Control'] = 'private, max-age=60'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@staff_member_required
def quotation_invoice_download(request, quotation_id):
    """Descarga directa de factura (solo con pago total)."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    if not (_quotation_is_fully_paid(q) or q.order_status in _fully_paid_statuses()):
        messages.warning(request, 'La factura solo está disponible cuando el pago es total.')
        return redirect('store:quotation_detail', quotation_id=q.id)
    iva_mode = _normalize_pdf_iva_mode(request.GET.get('iva', '1'))
    return redirect(
        reverse('store:quotation_pdf_file', kwargs={'quotation_id': q.id})
        + f'?iva={"1" if iva_mode == "with_iva" else "0"}&tipo=factura&download=1'
    )


def _quotation_rental_items(quote: Quotation):
    return list(
        quote.items.select_related('product', 'product__category', 'rental_price')
        .filter(product__product_type='rental')
        .order_by('id')
    )


def _rental_contract_context(quote: Quotation) -> dict:
    """Context for rental equipment contract PDF."""
    quote.sync_client_snapshot_from_profile(save=True)
    settings_obj = SiteSettings.load()
    rental_items = _quotation_rental_items(quote)
    equipment = []
    deposit_examples = []
    for it in rental_items:
        p = it.product
        tariffs = list(p.rental_prices.filter(is_active=True).order_by('order', 'period_type'))
        commercial = p.rental_commercial_value
        deposit_8pct = None
        if commercial is not None and commercial > 0:
            deposit_8pct = (commercial * Decimal('0.08')).quantize(Decimal('0.01'))
        entry = {
            'item': it,
            'product': p,
            'period_label': it.rental_price.get_period_type_display() if it.rental_price_id else 'Alquiler',
            'tariffs': tariffs,
            'commercial_value': commercial,
            'deposit_8pct': deposit_8pct,
        }
        equipment.append(entry)
        if deposit_8pct is not None:
            deposit_examples.append(entry)
    return {
        'quote': quote,
        'settings': settings_obj,
        'equipment': equipment,
        'deposit_examples': deposit_examples,
        'today': quote.created_at,
        'for_pdf_engine': True,
    }


def _build_rental_contract_pdf_bytes(quote: Quotation):
    """Generate rental contract PDF for quotation rental lines."""
    if not _quotation_rental_items(quote):
        return None, 'Esta cotización no incluye máquinas de alquiler.'

    try:
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO
    except ImportError:
        return None, 'xhtml2pdf no está instalado'

    template = get_template('store/rental_contract_pdf.html')
    html = template.render(_rental_contract_context(quote))
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        return None, f'Error generando contrato: {pdf.err}'
    return result.getvalue(), None


@xframe_options_sameorigin
def quotation_rental_contract(request, quotation_id):
    """Visor / descarga del contrato de alquiler asociado a la cotización."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    if not q.has_rental_items:
        messages.warning(request, 'Esta cotización no tiene máquinas de alquiler para generar contrato.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    as_download = str(request.GET.get('download') or '') in ('1', 'true', 'yes')
    pdf_bytes, err = _build_rental_contract_pdf_bytes(q)
    if not pdf_bytes:
        messages.error(request, err or 'No se pudo generar el contrato.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    safe_client = slugify(q.client_name or 'sin-cliente')[:40]
    filename = f"CONTRATO-ALQUILER-COT{q.id}-{q.created_at.strftime('%Y-%m-%d')}-{safe_client}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'attachment' if as_download else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    response['Cache-Control'] = 'private, max-age=60'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


def _save_data_url_image(field, data_url, filename_prefix):
    """Persist a canvas signature (data:image/png;base64,...) into an ImageField."""
    if not data_url or not str(data_url).startswith('data:image'):
        return False
    match = re.match(r'^data:image/(png|jpeg|jpg);base64,(.+)$', str(data_url).strip(), re.IGNORECASE | re.DOTALL)
    if not match:
        return False
    ext = match.group(1).lower()
    if ext == 'jpeg':
        ext = 'jpg'
    raw = base64.b64decode(match.group(2))
    field.save(f'{filename_prefix}.{ext}', ContentFile(raw), save=False)
    return True


@staff_member_required
def quotation_rental_requirements(request, quotation_id):
    """Captura datos del cliente, firmas digitales y fotos de cédula."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    if not q.has_rental_items:
        messages.warning(request, 'Esta cotización no tiene máquinas de alquiler.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    req, _ = RentalContractRequirements.objects.get_or_create(quotation=q)
    if not req.tenant_name:
        req.tenant_name = q.client_name or ''
    if not req.representative_name:
        settings_obj = SiteSettings.load()
        req.representative_name = settings_obj.company_rep_name or settings_obj.company_legal_name or 'MIXLAB SAS'

    if request.method == 'POST':
        client_document = (request.POST.get('client_document') or '').strip()
        client_email = (request.POST.get('client_email') or '').strip()
        client_phone = (request.POST.get('client_phone') or '').strip()

        errors = []
        if not client_document:
            errors.append('El número de cédula / documento es obligatorio.')
        if not client_email:
            errors.append('El correo del cliente es obligatorio.')
        else:
            try:
                validate_email(client_email)
            except ValidationError:
                errors.append('Ingresa un correo electrónico válido.')
        if not client_phone:
            errors.append('El teléfono del cliente es obligatorio.')
        if q.existing_client_id and len(client_phone) > 20:
            errors.append('El teléfono debe tener máximo 20 caracteres.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'store/quotation_rental_requirements.html', {
                'quote': q,
                'req': req,
                'posted_client_document': client_document,
                'posted_client_email': client_email,
                'posted_client_phone': client_phone,
            })

        # La cotización conserva una copia y, si hay cliente vinculado,
        # actualizamos también su usuario/perfil para que ningún PDF la sobrescriba.
        q.client_document = client_document
        q.client_email = client_email
        q.client_phone = client_phone
        q.save(update_fields=[
            'client_document',
            'client_email',
            'client_phone',
            'updated_at',
        ])
        if q.existing_client_id:
            client = q.existing_client
            if (client.email or '').strip() != client_email:
                client.email = client_email
                client.save(update_fields=['email'])
            profile = q._linked_client_profile()
            if profile:
                profile_fields = []
                if (profile.phone or '').strip() != client_phone:
                    profile.phone = client_phone
                    profile_fields.append('phone')
                if (getattr(profile, 'document_number', '') or '').strip() != client_document:
                    profile.document_number = client_document
                    profile_fields.append('document_number')
                if profile_fields:
                    profile_fields.append('updated_at')
                    profile.save(update_fields=profile_fields)

        req.representative_name = (request.POST.get('representative_name') or '').strip()
        req.tenant_name = (request.POST.get('tenant_name') or '').strip() or (q.client_name or '')
        req.notes = (request.POST.get('notes') or '').strip()

        _save_data_url_image(
            req.representative_signature,
            request.POST.get('representative_signature_data'),
            f'cot{q.id}-req-rep',
        )
        _save_data_url_image(
            req.tenant_signature,
            request.POST.get('tenant_signature_data'),
            f'cot{q.id}-req-tenant',
        )
        if request.FILES.get('id_front'):
            req.id_front = request.FILES['id_front']
        if request.FILES.get('id_back'):
            req.id_back = request.FILES['id_back']

        if req.is_complete and not req.completed_at:
            req.completed_at = timezone.now()
        elif not req.is_complete:
            req.completed_at = None
        req.save()
        messages.success(request, 'Requisitos del contrato guardados.')
        return redirect('store:quotation_rental_requirements', quotation_id=q.id)

    return render(request, 'store/quotation_rental_requirements.html', {
        'quote': q,
        'req': req,
    })


@staff_member_required
def ajax_reverse_geocode(request):
    """Devuelve una dirección aproximada a partir de lat/lng (Nominatim)."""
    if request.method != 'GET':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    lat = (request.GET.get('lat') or '').strip()
    lng = (request.GET.get('lng') or '').strip()
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Coordenadas inválidas'}, status=400)

    address = ''
    try:
        import json as _json
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode({
            'format': 'jsonv2',
            'lat': f'{lat_f:.6f}',
            'lon': f'{lng_f:.6f}',
            'zoom': 18,
            'addressdetails': 1,
            'accept-language': 'es',
        })
        url = f'https://nominatim.openstreetmap.org/reverse?{params}'
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'MixLab-Frozz/1.0 (acta-recepcion)',
                'Accept': 'application/json',
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode('utf-8'))
        address = (data.get('display_name') or '').strip()
    except Exception as exc:
        logger.warning('Reverse geocode failed: %s', exc)
        return JsonResponse({'ok': False, 'error': 'No se pudo obtener la dirección aproximada'}, status=502)

    return JsonResponse({
        'ok': True,
        'address': address,
        'maps_url': f'https://www.google.com/maps?q={lat_f:.6f},{lng_f:.6f}',
    })


@staff_member_required
def quotation_delivery_acta(request, quotation_id):
    """Acta de recepción: firmas + fotos + video + lugar al momento de la entrega."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    if not q.has_rental_items:
        messages.warning(request, 'Esta cotización no tiene máquinas de alquiler.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    acta, _ = RentalDeliveryActa.objects.get_or_create(quotation=q)
    if not acta.tenant_name:
        acta.tenant_name = q.client_name or ''
    if not acta.representative_name:
        settings_obj = SiteSettings.load()
        acta.representative_name = settings_obj.company_rep_name or settings_obj.company_legal_name or 'MIXLAB SAS'
    if not acta.delivered_at:
        acta.delivered_at = timezone.now()

    photo_fields = (
        ('photo_covers', 'Tapas y plásticos'),
        ('photo_lighting', 'Iluminación'),
        ('photo_buttons', 'Botones'),
        ('photo_radiator', 'Radiador'),
        ('photo_rear', 'Parte trasera'),
        ('photo_front', 'Parte delantera'),
    )

    if request.method == 'POST':
        acta.representative_name = (request.POST.get('representative_name') or '').strip()
        acta.tenant_name = (request.POST.get('tenant_name') or '').strip() or (q.client_name or '')
        acta.reception_location = (request.POST.get('reception_location') or '').strip()
        acta.reception_maps_url = (request.POST.get('reception_maps_url') or '').strip()
        acta.delivery_notes = (request.POST.get('delivery_notes') or '').strip()

        lat_raw = (request.POST.get('reception_latitude') or '').strip()
        lng_raw = (request.POST.get('reception_longitude') or '').strip()
        try:
            acta.reception_latitude = Decimal(lat_raw) if lat_raw else None
        except Exception:
            acta.reception_latitude = None
        try:
            acta.reception_longitude = Decimal(lng_raw) if lng_raw else None
        except Exception:
            acta.reception_longitude = None

        delivered_raw = (request.POST.get('delivered_at') or '').strip()
        if delivered_raw:
            try:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(delivered_raw)
                if parsed is None:
                    # datetime-local: 2026-07-15T16:00
                    parsed = parse_datetime(delivered_raw.replace('T', ' ') + ':00' if len(delivered_raw) == 16 else delivered_raw.replace('T', ' '))
                if parsed is not None:
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                    acta.delivered_at = parsed
            except Exception:
                pass

        _save_data_url_image(
            acta.representative_signature,
            request.POST.get('representative_signature_data'),
            f'cot{q.id}-acta-rep',
        )
        _save_data_url_image(
            acta.tenant_signature,
            request.POST.get('tenant_signature_data'),
            f'cot{q.id}-acta-tenant',
        )
        for field_name, _label in photo_fields:
            uploaded = request.FILES.get(field_name)
            if uploaded:
                setattr(acta, field_name, uploaded)

        video_uploaded = request.FILES.get('delivery_video')
        if video_uploaded:
            acta.delivery_video = video_uploaded

        if acta.is_complete and not acta.completed_at:
            acta.completed_at = timezone.now()
        elif not acta.is_complete:
            acta.completed_at = None
        acta.save()
        messages.success(request, 'Acta de recepción guardada.')
        if acta.is_complete:
            return redirect('store:quotation_detail', quotation_id=q.id)
        return redirect('store:quotation_delivery_acta', quotation_id=q.id)

    return render(request, 'store/quotation_delivery_acta.html', {
        'quote': q,
        'acta': acta,
        'photo_fields': [
            {
                'name': name,
                'label': label,
                'current': getattr(acta, name),
            }
            for name, label in photo_fields
        ],
    })


def _delivery_acta_pdf_context(quote: Quotation, acta: RentalDeliveryActa) -> dict:
    settings_obj = SiteSettings.load()
    return {
        'quote': quote,
        'acta': acta,
        'settings': settings_obj,
        'equipment': _quotation_rental_items(quote),
        'photos': [
            {'label': label, 'image': image}
            for _name, label, image in acta.photo_items()
            if image
        ],
        'for_pdf_engine': True,
    }


def _build_delivery_acta_pdf_bytes(quote: Quotation, acta: RentalDeliveryActa):
    """Generate delivery reception acta PDF with photos and signatures."""
    try:
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO
    except ImportError:
        return None, 'xhtml2pdf no está instalado'

    template = get_template('store/delivery_acta_pdf.html')
    html = template.render(_delivery_acta_pdf_context(quote, acta))
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        return None, f'Error generando acta: {pdf.err}'
    return result.getvalue(), None


@staff_member_required
@xframe_options_sameorigin
def quotation_delivery_acta_pdf(request, quotation_id):
    """Visor / descarga del acta de recepción completa."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    acta = RentalDeliveryActa.objects.filter(quotation=q).first()
    if not acta or not acta.is_complete:
        messages.warning(request, 'El acta de recepción aún no está completa.')
        return redirect('store:quotation_delivery_acta', quotation_id=q.id)

    as_download = str(request.GET.get('download') or '') in ('1', 'true', 'yes')
    pdf_bytes, err = _build_delivery_acta_pdf_bytes(q, acta)
    if not pdf_bytes:
        messages.error(request, err or 'No se pudo generar el acta.')
        return redirect('store:quotation_detail', quotation_id=q.id)

    safe_client = slugify(q.client_name or 'sin-cliente')[:40]
    stamp = (acta.completed_at or acta.updated_at or timezone.now()).strftime('%Y-%m-%d')
    filename = f"ACTA-RECEPCION-COT{q.id}-{stamp}-{safe_client}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'attachment' if as_download else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    response['Cache-Control'] = 'private, max-age=60'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@staff_member_required
def quotation_delete(request, quotation_id):
    """Eliminar una cotización (solo staff) con confirmación."""
    q = get_object_or_404(Quotation, id=quotation_id)
    # No permitir eliminar mientras espera pago
    if q.order_status == 'esperando_pago':
        messages.error(
            request,
            'No se puede eliminar una cotización que está en estado "Esperando pago".'
        )
        return redirect('store:quotation_list')
    # No permitir eliminar cotizaciones que ya tengan un estado de pedido post‑pago,
    # excepto si el usuario es superusuario (administrador total).
    post_payment_statuses = {'pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado'}
    if q.order_status in post_payment_statuses and not request.user.is_superuser:
        messages.error(
            request,
            'Solo un administrador puede eliminar una cotización que ya ha sido marcada como pagada/enviada/recibida.'
        )
        return redirect('store:quotation_detail', quotation_id=q.id)
    if request.method == 'POST':
        qid = q.id
        name = q.client_name or f'COT{qid}'
        q.delete()
        messages.success(request, f'Cotización {qid} ({name}) eliminada correctamente.')
        return redirect('store:quotation_list')
    return render(request, 'store/quotation_confirm_delete.html', {'quote': q})


def _absolute_url(path_or_url: str, request=None) -> str:
    """Build absolute URL from relative path when possible."""
    value = (path_or_url or '').strip()
    if not value:
        return ''
    if value.startswith('http://') or value.startswith('https://'):
        return value
    if request is not None:
        try:
            return request.build_absolute_uri(value)
        except Exception:
            pass
    from django.conf import settings
    base = getattr(settings, 'SITE_URL', '') or ''
    if base:
        return base.rstrip('/') + '/' + value.lstrip('/')
    return value


def _wa_money(amount) -> str:
    """Formato simple de dinero para WhatsApp."""
    try:
        return f"${Decimal(amount):.2f}"
    except Exception:
        return f"${amount}"


def _wa_build_message(title: str, lines: list[str], link: str = '') -> str:
    """
    Mensaje WhatsApp ordenado y minimalista.
    El enlace va dentro del texto (no como campo link separado).
    """
    parts = [title.strip()] if title else []
    for line in lines:
        text = (line or '').strip()
        if text:
            parts.append(text)
    url = (link or '').strip()
    if url:
        parts.append(url)
    return "\n".join(parts)


def _notify_whatsapp_n8n(*, message: str, link: str = '', phone: str = '', request=None) -> bool:
    """
    Envía notificación a WhatsApp vía webhook n8n.
    El enlace se incluye dentro de `message` para un formato limpio
    (sin preview / campo link separado).
    """
    try:
        settings_obj = SiteSettings.load()
    except Exception:
        logger.exception('[WA-N8N] No se pudo cargar SiteSettings')
        return False

    if not getattr(settings_obj, 'wa_n8n_enabled', True):
        logger.info('[WA-N8N] Notificaciones desactivadas')
        return False

    webhook = (getattr(settings_obj, 'wa_n8n_webhook_url', '') or '').strip()
    target = (phone or getattr(settings_obj, 'wa_n8n_phone', '') or '').strip()
    if not webhook:
        logger.warning('[WA-N8N] Falta wa_n8n_webhook_url')
        return False
    if not target:
        logger.warning('[WA-N8N] Falta teléfono / Group ID destino')
        return False

    absolute_link = _absolute_url(link, request=request) if link else ''
    final_message = (message or '').strip()
    if absolute_link and absolute_link not in final_message:
        final_message = _wa_build_message(final_message, [], link=absolute_link)

    payload = {
        'phone': target,
        # Vacío a propósito: el link ya va dentro de message (estilo pagos).
        'link': '',
        'message': final_message,
    }
    try:
        import requests
        resp = requests.post(webhook, json=payload, timeout=12)
        logger.info('[WA-N8N] POST %s status=%s phone=%s', webhook, resp.status_code, target)
        return 200 <= resp.status_code < 300
    except Exception:
        logger.exception('[WA-N8N] Error enviando webhook')
        return False


def _notify_wa_new_quotation(quote: Quotation, *, source: str = '', request=None) -> None:
    """WhatsApp: nueva cotización (formato minimalista)."""
    quote.sync_client_snapshot_from_profile(save=True)
    items = list(quote.items.select_related('product')[:6])
    lines_items = []
    for it in items:
        name = getattr(it.product, 'name', 'Producto')
        lines_items.append(f"• {name} x{it.quantity}")
    more = quote.items.count() - len(items)
    if more > 0:
        lines_items.append(f"• … y {more} más")

    source_label = source or ('Cliente registrado' if quote.existing_client_id else 'Cotización')
    lines = [
        f"COT-{quote.id}",
        f"Origen: {source_label}",
        f"Cliente: {quote.display_client_name or '—'}",
        f"Tel: {quote.display_client_phone or '—'}",
        f"Correo: {quote.display_client_email or '—'}",
        f"Total: {_wa_money(quote.total)}",
    ]
    if lines_items:
        lines.append("Productos:")
        lines.extend(lines_items)

    link = ''
    if request is not None:
        try:
            link = request.build_absolute_uri(reverse('store:quotation_detail', kwargs={'quotation_id': quote.id}))
        except Exception:
            link = f"/cotizaciones/{quote.id}/"
    else:
        link = f"/cotizaciones/{quote.id}/"

    message = _wa_build_message('🧊 *Nueva cotización*', lines, link=_absolute_url(link, request=request))
    _notify_whatsapp_n8n(message=message, link='', request=request)


def _notify_wa_quotation_payment(quote: Quotation, *, event: str = 'referencia', request=None) -> None:
    """WhatsApp: pago / referencia de cotización (formato minimalista)."""
    quote.sync_client_snapshot_from_profile(save=True)
    if event == 'pago_recibido':
        title = '💳 *Pago total de cotización*'
    elif event == 'pago_parcial':
        title = '💵 *Pago parcial de cotización*'
    else:
        title = '📎 *Referencia de pago subida*'

    lines = [
        f"COT-{quote.id}",
        f"Cliente: {quote.display_client_name or '—'}",
        f"Tel: {quote.display_client_phone or '—'}",
        f"Estado pedido: {quote.get_order_status_display()}",
        f"Total: {_wa_money(quote.total)}",
    ]
    if event == 'pago_parcial' and quote.partial_payment_amount:
        lines.append(f"Abono: {_wa_money(quote.partial_payment_amount)}")
        lines.append(f"Saldo: {_wa_money(quote.remaining_balance)}")
    elif event == 'pago_recibido':
        lines.append('Pago: Total')

    link = ''
    if request is not None:
        try:
            link = request.build_absolute_uri(reverse('store:quotation_detail', kwargs={'quotation_id': quote.id}))
        except Exception:
            link = f"/cotizaciones/{quote.id}/"
        if quote.payment_proof:
            try:
                link = request.build_absolute_uri(quote.payment_proof.url)
            except Exception:
                link = getattr(quote.payment_proof, 'url', link) or link
    else:
        link = f"/cotizaciones/{quote.id}/"

    message = _wa_build_message(title, lines, link=_absolute_url(link, request=request))
    _notify_whatsapp_n8n(message=message, link='', request=request)


def _notify_wa_finance_record(record: FinanceRecord, request=None) -> None:
    """WhatsApp: gasto o pago registrado en caja (formato minimalista)."""
    emoji = '📉' if record.record_type == 'gasto' else '📈'
    title = f"{emoji} *{record.get_record_type_display()} registrado*"
    lines = [
        f"Monto: {_wa_money(record.amount)}",
        f"Categoría: {record.get_category_display()}",
        f"Descripción: {record.description}",
        f"Fecha: {record.recorded_at}",
    ]
    if record.related_quotation_id:
        lines.append(f"Cotización: COT-{record.related_quotation_id}")
    if record.notes:
        lines.append(f"Notas: {record.notes}")
    if record.created_by_id:
        lines.append(f"Por: {record.created_by.get_full_name() or record.created_by.username}")

    link = ''
    if request is not None:
        try:
            link = request.build_absolute_uri(reverse('store:finance_list'))
        except Exception:
            link = '/manager/finanzas/'
        if record.receipt:
            try:
                link = request.build_absolute_uri(record.receipt.url)
            except Exception:
                link = getattr(record.receipt, 'url', link) or link
    else:
        link = '/manager/finanzas/'

    message = _wa_build_message(title, lines, link=_absolute_url(link, request=request))
    _notify_whatsapp_n8n(message=message, link='', request=request)


def _notify_telegram_new_quotation(quote: Quotation, is_registered: bool) -> None:
    """Envía alerta a Telegram con datos de la cotización y el PDF adjunto. Requiere TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en settings."""
    from django.conf import settings
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
    logger.info(
        "[TELEGRAM] Preparando envío. token_set=%s chat_id=%r quote_id=%s",
        bool(token),
        chat_id,
        getattr(quote, "id", None),
    )
    if not token or not chat_id:
        logger.warning("[TELEGRAM] Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID; no se enviará mensaje")
        return
    try:
        import requests
    except Exception:
        logger.exception("[TELEGRAM] No se pudo importar requests; omitiendo notificación")
        return

    tipo = 'Registrado' if is_registered and quote.existing_client_id else 'Invitado / Anónimo'
    lineas = [
        f"🧊 Nueva cotización / pedido #{quote.id}",
        f"Tipo de cliente: {tipo}",
        f"Nombre: {quote.client_name or '—'}",
        f"Correo: {quote.client_email or '—'}",
        f"Teléfono (WhatsApp): {quote.client_phone or '—'}",
        f"Ubicación: {quote.display_client_departamento or '—'} - {quote.display_client_city or '—'}",
        f"Total: {quote.total} COP",
    ]
    if quote.notes:
        lineas.append(f"Notas: {quote.notes}")

    text = "\n".join(lineas)
    
    # Enviar mensaje de texto primero
    try:
        logger.info("[TELEGRAM] Enviando mensaje a chat_id=%r", chat_id)
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
            },
            timeout=5,
        )
        logger.info(
            "[TELEGRAM] Mensaje texto status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:300],
        )
    except Exception:
        logger.exception("[TELEGRAM] Error al enviar mensaje de texto")
        # Continuar intentando enviar PDF aunque falle el texto

    # Generar y enviar PDF
    try:
        from io import BytesIO

        pdf_bytes, err = _build_quotation_pdf_bytes(quote)
        if not pdf_bytes:
            logger.warning("[TELEGRAM] No se pudo generar PDF: %s", err)
            return

        safe_client = slugify(quote.client_name or 'sin-cliente')[:40]
        safe_date = quote.created_at.strftime('%Y-%m-%d')
        filename = f"COT{quote.id}-{safe_date}-{safe_client}.pdf"

        # Enviar PDF como documento
        logger.info("[TELEGRAM] Enviando PDF (%d bytes) a chat_id=%r", len(pdf_bytes), chat_id)
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={
                'chat_id': chat_id,
                'caption': f'📄 PDF de la cotización COT{quote.id}',
            },
            files={
                'document': (filename, BytesIO(pdf_bytes), 'application/pdf'),
            },
            timeout=10,
        )
        logger.info(
            "[TELEGRAM] PDF status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:300],
        )
    except ImportError:
        logger.warning("[TELEGRAM] xhtml2pdf no está instalado; no se enviará PDF")
    except Exception:
        logger.exception("[TELEGRAM] Error al generar o enviar PDF")


def _parse_quote_line_key(key):
    """Parse session key 'productId' or 'productId:rentalPriceId'."""
    parts = str(key).split(':')
    try:
        product_id = int(parts[0])
    except (TypeError, ValueError):
        return None, None
    rental_price_id = None
    if len(parts) >= 2 and parts[1]:
        try:
            rental_price_id = int(parts[1])
        except (TypeError, ValueError):
            rental_price_id = None
    return product_id, rental_price_id


def _normalize_quote_entry(raw) -> dict:
    """Normalize session line to {qty, discount_type, discount_value, rental_price_id}."""
    qty = 1
    discount_value = Decimal('0.00')
    discount_type = 'percent'
    rental_price_id = None
    if isinstance(raw, dict):
        try:
            qty = int(raw.get('qty', 1))
        except (TypeError, ValueError):
            qty = 1
        raw_type = str(raw.get('discount_type') or 'percent').strip().lower()
        discount_type = 'amount' if raw_type in ('amount', 'value', 'fixed', '$', 'cop') else 'percent'
        # Compat: discount_value nuevo; si no, discount_percent legado
        raw_disc = raw.get('discount_value', None)
        if raw_disc is None:
            raw_disc = raw.get('discount_percent', 0)
        try:
            discount_value = Decimal(str(raw_disc).replace(',', '.'))
        except Exception:
            discount_value = Decimal('0.00')
        try:
            rid = raw.get('rental_price_id')
            rental_price_id = int(rid) if rid not in (None, '', 'null') else None
        except (TypeError, ValueError):
            rental_price_id = None
    else:
        try:
            qty = int(raw)
        except (TypeError, ValueError):
            qty = 1
    if qty < 1:
        qty = 1
    if discount_value < 0:
        discount_value = Decimal('0.00')
    if discount_type == 'percent' and discount_value > 100:
        discount_value = Decimal('100.00')
    discount_value = discount_value.quantize(Decimal('0.01'))
    return {
        'qty': qty,
        'discount_type': discount_type,
        'discount_value': float(discount_value),
        # Compat lectura templates/JS antiguos
        'discount_percent': float(discount_value) if discount_type == 'percent' else 0.0,
        'rental_price_id': rental_price_id,
    }


def _quote_base_unit_price(product, rental_price_id=None) -> Decimal:
    """Catalog/list unit price before line discount (supports rental tariffs)."""
    if rental_price_id:
        tariff = ProductRentalPrice.objects.filter(
            id=rental_price_id,
            product_id=product.id,
            is_active=True,
        ).first()
        if tariff:
            return tariff.price
    return product.selling_price or Decimal('0.00')


def _quote_unit_price(
    product,
    discount_value=0,
    rental_price_id=None,
    discount_type='percent',
    discount_percent=None,
) -> Decimal:
    """Unit price after optional line discount (% or fixed amount)."""
    base = _quote_base_unit_price(product, rental_price_id=rental_price_id)
    # Compat: callers antiguos solo pasan discount_percent
    if discount_percent is not None and (discount_value is None or discount_value == 0):
        discount_value = discount_percent
        discount_type = 'percent'
    try:
        disc = Decimal(str(discount_value or 0))
    except Exception:
        disc = Decimal('0.00')
    if disc <= 0:
        return base

    dtype = str(discount_type or 'percent').strip().lower()
    if dtype in ('amount', 'value', 'fixed', '$', 'cop'):
        if disc > base:
            disc = base
        return (base - disc).quantize(Decimal('0.01'))

    if disc > 100:
        disc = Decimal('100.00')
    factor = (Decimal('100') - disc) / Decimal('100')
    return (base * factor).quantize(Decimal('0.01'))


def _get_quote_session(request) -> dict:
    """Return quotation session: {line_key: {qty, discount_type, discount_value, rental_price_id}}"""
    data = request.session.get('quotation', {})
    if not isinstance(data, dict):
        data = {}
    clean: dict[str, dict] = {}
    for k, v in data.items():
        product_id, rental_from_key = _parse_quote_line_key(k)
        if product_id is None:
            continue
        entry = _normalize_quote_entry(v)
        if rental_from_key and not entry.get('rental_price_id'):
            entry['rental_price_id'] = rental_from_key
        if entry.get('rental_price_id'):
            line_key = f"{product_id}:{entry['rental_price_id']}"
        else:
            line_key = str(product_id)
        clean[line_key] = entry
    request.session['quotation'] = clean
    request.session.modified = True
    return clean


def _quote_payload(request) -> dict:
    """Build JSON payload for current quotation session."""
    q = _get_quote_session(request)
    product_ids = set()
    rental_ids = set()
    for key, entry in q.items():
        pid, rid = _parse_quote_line_key(key)
        if pid is None:
            continue
        product_ids.add(pid)
        rid = entry.get('rental_price_id') or rid
        if rid:
            rental_ids.add(rid)

    products = Product.objects.filter(id__in=product_ids).select_related('category')
    by_id = {p.id: p for p in products}
    tariffs = {
        t.id: t
        for t in ProductRentalPrice.objects.filter(id__in=rental_ids, is_active=True).select_related('product')
    }

    items = []
    total = Decimal('0.00')
    total_base = Decimal('0.00')
    total_iva = Decimal('0.00')

    def split_iva(amount: Decimal):
        if amount is None:
            amount = Decimal('0.00')
        base = (amount / (Decimal('1.00') + IVA_RATE))
        iva = amount - base
        return base, iva

    for line_key, entry in q.items():
        pid, rid_from_key = _parse_quote_line_key(line_key)
        p = by_id.get(pid)
        if not p:
            continue
        qty = entry['qty']
        discount_type = entry.get('discount_type') or 'percent'
        discount_value = entry.get('discount_value', entry.get('discount_percent', 0))
        rental_price_id = entry.get('rental_price_id') or rid_from_key
        tariff = tariffs.get(rental_price_id) if rental_price_id else None

        list_unit = _quote_base_unit_price(p, rental_price_id=rental_price_id)
        unit = _quote_unit_price(
            p,
            discount_value=discount_value,
            discount_type=discount_type,
            rental_price_id=rental_price_id,
        )
        subtotal = unit * qty
        total += subtotal
        base_subtotal, iva_subtotal = split_iva(subtotal)
        base_unit, iva_unit = split_iva(unit)
        total_base += base_subtotal
        total_iva += iva_subtotal

        discount_unit = (list_unit - unit) if unit < list_unit else Decimal('0.00')
        discount_total = discount_unit * qty
        display_name = p.name
        period_label = ''
        if tariff:
            period_label = tariff.get_period_type_display()
            display_name = f'{p.name} · {period_label}'

        items.append({
            'id': p.id,
            'line_key': line_key,
            'name': display_name,
            'category': p.category.name,
            'image_url': p.image.url if p.image else '',
            'qty': qty,
            'discount_type': discount_type,
            'discount_value': float(discount_value),
            'discount_percent': float(discount_value) if discount_type == 'percent' else 0.0,
            'rental_price_id': rental_price_id,
            'period_label': period_label,
            'list_unit_price': float(list_unit),
            'unit_price': float(unit),
            'unit_base': float(base_unit),
            'unit_iva': float(iva_unit),
            'original_unit_price': float(p.price),
            'discount_unit': float(discount_unit),
            'discount_total': float(discount_total),
            'subtotal': float(subtotal),
            'subtotal_base': float(base_subtotal),
            'subtotal_iva': float(iva_subtotal),
        })
    return {
        'items': items,
        'total': float(total),
        'total_base': float(total_base),
        'total_iva': float(total_iva),
    }


def quotation_ajax_add(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    q = _get_quote_session(request)
    ids = request.POST.getlist('products[]') or request.POST.getlist('products') or []
    added = 0
    for raw in ids:
        raw = str(raw).strip()
        if not raw:
            continue
        product_id, rental_price_id = _parse_quote_line_key(raw)
        if product_id is None:
            continue
        if not Product.objects.filter(id=product_id, available=True).exists():
            continue
        if rental_price_id:
            if not ProductRentalPrice.objects.filter(
                id=rental_price_id, product_id=product_id, is_active=True
            ).exists():
                continue
            key = f'{product_id}:{rental_price_id}'
        else:
            # Alquileres deben agregarse por tarifa (hora/día/semana/mes)
            prod = Product.objects.filter(id=product_id, available=True).only('id', 'product_type').first()
            if not prod:
                continue
            if prod.is_rental:
                continue
            key = str(product_id)
            rental_price_id = None
        if key not in q:
            q[key] = {
                'qty': 1,
                'discount_type': 'percent',
                'discount_value': 0.0,
                'discount_percent': 0.0,
                'rental_price_id': rental_price_id,
            }
            added += 1
    request.session['quotation'] = q
    request.session.modified = True
    payload = _quote_payload(request)
    payload['added'] = added
    return JsonResponse(payload)


def quotation_ajax_remove(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    q = _get_quote_session(request)
    line_key = (request.POST.get('line_key') or request.POST.get('product_id') or '').strip()
    if not line_key:
        return JsonResponse({'error': 'Invalid product_id'}, status=400)
    # Compat: si llega solo product_id numérico, borra esa clave
    q.pop(line_key, None)
    # También limpia claves legacy del producto sin tarifa
    pid, _ = _parse_quote_line_key(line_key)
    if pid is not None and ':' not in line_key:
        q.pop(str(pid), None)
    request.session['quotation'] = q
    request.session.modified = True
    return JsonResponse(_quote_payload(request))


def quotation_ajax_update_qty(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    q = _get_quote_session(request)
    line_key = (request.POST.get('line_key') or request.POST.get('product_id') or '').strip()
    qty = request.POST.get('qty')
    try:
        qty_int = int(qty)
        if qty_int < 1:
            qty_int = 1
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid data'}, status=400)
    if line_key in q:
        entry = _normalize_quote_entry(q[line_key])
        entry['qty'] = qty_int
        q[line_key] = entry
        request.session['quotation'] = q
        request.session.modified = True
    return JsonResponse(_quote_payload(request))


def quotation_ajax_update_discount(request):
    """Set line discount as percent (0-100) or fixed amount (COP per unit)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    q = _get_quote_session(request)
    line_key = (request.POST.get('line_key') or request.POST.get('product_id') or '').strip()
    raw_type = str(request.POST.get('discount_type') or 'percent').strip().lower()
    discount_type = 'amount' if raw_type in ('amount', 'value', 'fixed', '$', 'cop') else 'percent'
    discount_raw = request.POST.get('discount_value', request.POST.get('discount_percent', '0'))
    try:
        discount = Decimal(str(discount_raw).replace(',', '.'))
    except (ValueError, TypeError, Exception):
        return JsonResponse({'error': 'Invalid data'}, status=400)
    if discount < 0:
        discount = Decimal('0.00')
    if discount_type == 'percent' and discount > 100:
        discount = Decimal('100.00')
    if line_key in q:
        entry = _normalize_quote_entry(q[line_key])
        # Cap amount to list price when possible
        if discount_type == 'amount':
            pid, rid = _parse_quote_line_key(line_key)
            rid = entry.get('rental_price_id') or rid
            try:
                product = Product.objects.get(id=pid, available=True)
                max_amount = _quote_base_unit_price(product, rental_price_id=rid)
                if discount > max_amount:
                    discount = max_amount
            except Product.DoesNotExist:
                pass
        entry['discount_type'] = discount_type
        entry['discount_value'] = float(discount.quantize(Decimal('0.01')))
        entry['discount_percent'] = entry['discount_value'] if discount_type == 'percent' else 0.0
        q[line_key] = entry
        request.session['quotation'] = q
        request.session.modified = True
    return JsonResponse(_quote_payload(request))


# --- Calculadora de dilución con agua ---

def water_calculator(request):
    """Hub de calculadoras: dilución (ML) y costos (cálculo en cliente)."""
    products = DilutionBaseProduct.objects.filter(is_active=True).order_by('sort_order', 'name')
    return render(request, 'store/water_calculator.html', {'products': products})


@staff_member_required
def dilution_product_list(request):
    """Listado admin de productos base para la calculadora."""
    items = DilutionBaseProduct.objects.all().order_by('sort_order', 'name')
    return render(request, 'store/inventory/dilution_product_list.html', {'items': items})


@staff_member_required
def dilution_product_create(request):
    """Crear producto base para la calculadora."""
    if request.method == 'POST':
        form = DilutionBaseProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto base agregado a la calculadora.')
            return redirect('store:dilution_product_list')
    else:
        form = DilutionBaseProductForm()
    return render(request, 'store/inventory/dilution_product_form.html', {
        'form': form,
        'title': 'Nuevo producto base',
    })


@staff_member_required
def dilution_product_edit(request, item_id):
    """Editar producto base de la calculadora."""
    item = get_object_or_404(DilutionBaseProduct, id=item_id)
    if request.method == 'POST':
        form = DilutionBaseProductForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto base actualizado.')
            return redirect('store:dilution_product_list')
    else:
        form = DilutionBaseProductForm(instance=item)
    return render(request, 'store/inventory/dilution_product_form.html', {
        'form': form,
        'title': 'Editar producto base',
        'item': item,
    })


@staff_member_required
def dilution_product_delete(request, item_id):
    """Eliminar producto base de la calculadora."""
    item = get_object_or_404(DilutionBaseProduct, id=item_id)
    if request.method == 'POST':
        name = item.name
        item.delete()
        messages.success(request, f'"{name}" eliminado de la calculadora.')
        return redirect('store:dilution_product_list')
    return render(request, 'store/inventory/dilution_product_confirm_delete.html', {'item': item})


@staff_member_required
def site_settings_edit(request):
    """Editar contacto, redes sociales, WhatsApp y métodos de pago del sitio."""
    settings_obj = SiteSettings.load()
    payment_methods = PaymentMethod.objects.all().order_by('sort_order', 'id')
    editing_payment = None
    payment_form = PaymentMethodForm()

    if request.method == 'GET' and request.GET.get('edit_payment'):
        try:
            editing_payment = PaymentMethod.objects.get(id=int(request.GET.get('edit_payment')))
            payment_form = PaymentMethodForm(instance=editing_payment)
        except (PaymentMethod.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Método de pago no encontrado.')
            return redirect('store:site_settings_edit')

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save_settings').strip()

        if action == 'add_payment':
            payment_form = PaymentMethodForm(request.POST, request.FILES)
            if payment_form.is_valid():
                payment_form.save()
                messages.success(request, 'Método de pago agregado.')
                return redirect('store:site_settings_edit')
            messages.error(request, 'Revisa los datos del método de pago.')
            form = SiteSettingsForm(instance=settings_obj)
            return render(request, 'store/inventory/site_settings_form.html', {
                'form': form,
                'settings_obj': settings_obj,
                'payment_methods': payment_methods,
                'payment_form': payment_form,
                'editing_payment': None,
            })

        if action == 'edit_payment':
            try:
                editing_payment = PaymentMethod.objects.get(id=int(request.POST.get('payment_id') or 0))
            except (PaymentMethod.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'No se pudo actualizar el método de pago.')
                return redirect('store:site_settings_edit')
            payment_form = PaymentMethodForm(request.POST, request.FILES, instance=editing_payment)
            if payment_form.is_valid():
                payment_form.save()
                messages.success(request, 'Método de pago actualizado.')
                return redirect('store:site_settings_edit')
            messages.error(request, 'Revisa los datos del método de pago.')
            form = SiteSettingsForm(instance=settings_obj)
            return render(request, 'store/inventory/site_settings_form.html', {
                'form': form,
                'settings_obj': settings_obj,
                'payment_methods': payment_methods,
                'payment_form': payment_form,
                'editing_payment': editing_payment,
            })

        if action == 'delete_payment':
            try:
                item_id = int(request.POST.get('payment_id') or 0)
                item = PaymentMethod.objects.get(id=item_id)
                item.delete()
                messages.success(request, 'Método de pago eliminado.')
            except (PaymentMethod.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'No se pudo eliminar el método de pago.')
            return redirect('store:site_settings_edit')

        if action == 'toggle_payment':
            try:
                item_id = int(request.POST.get('payment_id') or 0)
                item = PaymentMethod.objects.get(id=item_id)
                item.is_active = not item.is_active
                item.save(update_fields=['is_active', 'updated_at'])
                messages.success(request, 'Estado del método de pago actualizado.')
            except (PaymentMethod.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'No se pudo actualizar el método de pago.')
            return redirect('store:site_settings_edit')

        form = SiteSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuración del sitio actualizada.')
            return redirect('store:site_settings_edit')
    else:
        form = SiteSettingsForm(instance=settings_obj)

    return render(request, 'store/inventory/site_settings_form.html', {
        'form': form,
        'settings_obj': settings_obj,
        'payment_methods': payment_methods,
        'payment_form': payment_form,
        'editing_payment': editing_payment,
    })


def _drinzz_contract_additional_paragraphs(contract: DrinzzContractConfig):
    raw = (contract.additional_clauses or '').strip()
    if not raw:
        return []
    parts = []
    for block in raw.replace('\r\n', '\n').split('\n'):
        line = block.strip()
        if line:
            parts.append(line)
    return parts


def _build_drinzz_contract_pdf_bytes(contract=None):
    """Genera PDF del contrato marco Drinzz."""
    try:
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO
    except ImportError:
        return None, 'xhtml2pdf no está instalado'

    contract = contract or DrinzzContractConfig.load()
    site = SiteSettings.load()
    # Completar datos legales vacíos desde SiteSettings
    if not (contract.operator_legal_name or '').strip():
        contract.operator_legal_name = site.company_legal_name
    if not (contract.operator_nit or '').strip():
        contract.operator_nit = site.company_nit
    if not (contract.operator_address or '').strip():
        contract.operator_address = site.company_address
    if not (contract.operator_rep_name or '').strip():
        contract.operator_rep_name = site.company_rep_name
    if not (contract.operator_city or '').strip():
        contract.operator_city = site.address_city or site.jurisdiction_city

    template = get_template('store/drinzz_contract_pdf.html')
    html = template.render({
        'contract': contract,
        'settings': site,
        'additional_paragraphs': _drinzz_contract_additional_paragraphs(contract),
        'today': timezone.now(),
        'for_pdf_engine': True,
    })
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=_pdf_link_callback,
    )
    if pdf.err:
        return None, 'Error al generar el PDF del contrato Drinzz'
    return result.getvalue(), None


@staff_member_required
def drinzz_contract_edit(request):
    """Admin: editar términos del contrato marco Drinzz."""
    contract = DrinzzContractConfig.load()
    if request.method == 'POST':
        form = DrinzzContractConfigForm(request.POST, instance=contract)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contrato Drinzz actualizado.')
            return redirect('store:drinzz_contract_edit')
    else:
        form = DrinzzContractConfigForm(instance=contract)
    return render(request, 'store/inventory/drinzz_contract_form.html', {
        'form': form,
        'contract': contract,
    })


def drinzz_contract_pdf(request):
    """PDF público del contrato marco Drinzz (si está publicado) o staff siempre."""
    contract = DrinzzContractConfig.load()
    if not contract.is_published and not (request.user.is_authenticated and request.user.is_staff):
        return HttpResponse('El contrato no está publicado.', status=404, content_type='text/plain; charset=utf-8')

    pdf_bytes, err = _build_drinzz_contract_pdf_bytes(contract)
    if not pdf_bytes:
        return HttpResponse(err or 'No se pudo generar el PDF', status=500, content_type='text/plain; charset=utf-8')

    filename = f"contrato-drinzz-{slugify(contract.version_label) or 'v1'}.pdf"
    as_download = str(request.GET.get('download') or '') in ('1', 'true', 'yes')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'attachment' if as_download else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    return response
