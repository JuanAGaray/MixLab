import os
import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.text import slugify
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Min, Max, Sum, Prefetch
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from decimal import Decimal

from .models import (
    Product, Category, Cart, CartItem, Order, OrderItem,
    ProductImage, ProductVariation, ProductVariationImage, ProductTechnicalSpec, ProductAttribute
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
)
from .models import Quotation, QuotationItem

# IVA en Colombia (por defecto 19%). Los precios ya incluyen IVA en este proyecto.
IVA_RATE = Decimal('0.19')

logger = logging.getLogger(__name__)


def _deduct_stock_for_quotation(quotation: Quotation):
    """
    Descontar stock de los productos de una cotización.
    Se llama una sola vez cuando el estado de pedido pasa por primera vez a un estado post‑pago.
    """
    items = quotation.items.select_related('product')
    for it in items:
        product = it.product
        if not product:
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


def home(request):
    """Home page with featured products"""
    featured_products = Product.objects.filter(available=True)[:8]
    
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
        # For anonymous users, get from session
        session_cart = request.session.get('cart', {})
        for product_id_str, quantity in session_cart.items():
            try:
                product_id = int(product_id_str)
                cart_quantities[product_id] = quantity
            except (ValueError, TypeError):
                continue
    
    # Attach cart quantities to products
    for product in featured_products:
        product.cart_quantity = cart_quantities.get(product.id, 0)
    
    context = {
        'featured_products': featured_products,
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
    
    related_products = Product.objects.filter(
        category=product.category,
        available=True
    ).exclude(id=product.id)[:4]

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

            quotation_obj = Quotation.objects.create(
                created_by=user,
                existing_client=user,
                client_kind='existing',
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
            messages.success(request, f'Cliente "{client.get_full_name() or client.username}" actualizado.')
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


# Inventory views (staff only)
@staff_member_required
def inventory_dashboard(request):
    """Inventory dashboard"""
    total_products = Product.objects.count()
    available_products = Product.objects.filter(available=True).count()
    low_stock_products = Product.objects.filter(stock__lt=5, stock__gt=0).count()
    out_of_stock_products = Product.objects.filter(stock=0).count()
    products = Product.objects.all().order_by('-created_at')
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'total_products': total_products,
        'available_products': available_products,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'page_obj': page_obj,
    }
    return render(request, 'store/inventory/dashboard.html', context)


@staff_member_required
def inventory_list(request):
    """List all products for inventory management"""
    products = Product.objects.all().order_by('-created_at')
    
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
    }
    return render(request, 'store/inventory/product_form.html', context)


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
            product.save(update_fields=['name', 'slug', 'category_id', 'product_type', 'description', 'keywords'])
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
                product.purchase_cost = Decimal(str(request.POST.get('purchase_cost', product.purchase_cost) or 0))
                product.price = Decimal(str(request.POST.get('price', product.price) or 0))
                pr = request.POST.get('promotional_price')
                product.promotional_price = Decimal(pr) if pr else None
                product.stock = int(request.POST.get('stock', product.stock) or 0)
                product.available = request.POST.get('available') == 'on'
                product.save(update_fields=['purchase_cost', 'price', 'promotional_price', 'stock', 'available'])
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
    )

    for attr in product.attributes.all():
        ProductAttribute.objects.create(
            product=new_product,
            key=attr.key,
            value=attr.value,
            order=attr.order,
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
    else:
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
    quotation_items = []
    total = Decimal('0.00')
    
    # Si hay sesión de cotización, úsala como base (AJAX)
    session_quote = _get_quote_session(request)
    if session_quote:
        for pid_str, qty in session_quote.items():
            try:
                product = Product.objects.get(id=int(pid_str), available=True)
                price = product.selling_price
                subtotal = price * qty
                total += subtotal
                quotation_items.append({
                    'product': product,
                    'quantity': qty,
                    'unit_price': price,
                    'subtotal': subtotal,
                })
            except (Product.DoesNotExist, ValueError):
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
                # phone desde perfil si existe
                client_phone = ''
                try:
                    client_phone = getattr(getattr(selected_client, 'profile', None), 'phone', '') or ''
                except Exception:
                    client_phone = ''
                client_kind = 'existing'
                client_departamento = ''
                client_city = ''
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
            for pid_str, qty in session_quote.items():
                try:
                    product = Product.objects.get(id=int(pid_str), available=True)
                except (Product.DoesNotExist, ValueError):
                    continue
                price = product.selling_price
                item = QuotationItem.objects.create(
                    quotation=quotation_obj,
                    product=product,
                    quantity=qty,
                    unit_price=price,
                    subtotal=price * qty,
                )
                running_total += item.subtotal

            quotation_obj.total = running_total
            quotation_obj.save(update_fields=['total', 'updated_at'])

            # Limpiar sesión de cotización
            request.session['quotation'] = {}
            request.session.modified = True

            messages.success(request, f'Cotización #{quotation_obj.id} generada exitosamente.')
            return redirect('store:quotation_detail', quotation_id=quotation_obj.id)
    else:
        form = QuotationForm()
        # Obtener productos desde GET (pueden venir desde la lista de productos)
        product_ids = request.GET.getlist('products')
        
        # Eliminar duplicados manteniendo el orden
        seen = set()
        unique_product_ids = []
        for pid in product_ids:
            try:
                pid_int = int(pid)
                if pid_int not in seen:
                    seen.add(pid_int)
                    unique_product_ids.append(pid_int)
            except (ValueError, TypeError):
                continue
        
        # Construir items de cotización (y persistir a sesión)
        for pid in unique_product_ids:
            try:
                product = Product.objects.get(id=pid, available=True)
                price = product.selling_price
                # si ya venía desde sesión, no duplicar
                already = any(it['product'].id == product.id for it in quotation_items)
                if already:
                    continue
                quotation_items.append({
                    'product': product,
                    'quantity': 1,
                    'unit_price': price,
                    'subtotal': price,
                })
                total += price
                session_quote[str(product.id)] = 1
            except (Product.DoesNotExist, ValueError):
                continue
        request.session['quotation'] = session_quote
        request.session.modified = True
    
    # Lista de todos los productos disponibles agrupados por categoría
    # Excluir productos ya en la cotización solo si hay productos seleccionados
    selected_product_ids = [item['product'].id for item in quotation_items] if quotation_items else []
    if selected_product_ids:
        all_products = Product.objects.filter(available=True).exclude(id__in=selected_product_ids).select_related('category').order_by('category__name', 'name')
    else:
        all_products = Product.objects.filter(available=True).select_related('category').order_by('category__name', 'name')
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
        'total': total,
        'all_products': all_products,
        'products_by_category': products_by_category,
        'categories': categories,
        'clients': clients,
    }
    return render(request, 'store/quotation.html', context)


@staff_member_required
def quotation_list(request):
    """Listado (registro) de cotizaciones realizadas con filtros por cliente, manager y estado."""
    quotes = Quotation.objects.select_related('existing_client', 'created_by').order_by('-created_at')
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
    """Vista de ventas: cotizaciones con estado de pedido 'pago_recibido'."""
    quotes = (
        Quotation.objects
        .filter(order_status='pago_recibido')
        .select_related('existing_client', 'created_by')
        .order_by('-created_at')
    )
    return render(request, 'store/manager/sales_list.html', {'quotes': quotes})


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
    if qs and qs in allowed_qs and qs != qobj.quotation_status:
        qobj.quotation_status = qs
        update_fields.extend(['quotation_status'])
    if os_ and os_ in allowed_os and os_ != qobj.order_status:
        # Estados que requieren comprobante de pago antes de avanzar
        post_payment_statuses = {'pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado'}
        if os_ in post_payment_statuses and not qobj.payment_proof:
            return JsonResponse({
                'error': 'Debe subir una referencia de pago en el detalle de la cotización antes de marcar este estado.',
            }, status=400)
        # No permitir bajar de un estado post‑pago a uno previo
        if qobj.order_status in post_payment_statuses and os_ not in post_payment_statuses:
            return JsonResponse({
                'error': 'No es posible regresar el estado del pedido una vez que ha sido marcado como pagado/enviado/recibido.',
            }, status=400)
        # Si pasamos por primera vez a un estado post‑pago, descontar stock
        previous_status = qobj.order_status
        if os_ in post_payment_statuses and previous_status not in post_payment_statuses:
            _deduct_stock_for_quotation(qobj)
        qobj.order_status = os_
        update_fields.extend(['order_status'])
    if update_fields:
        update_fields.append('updated_at')
        qobj.save(update_fields=update_fields)
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

    # Subir referencia de pago (solo staff)
    if request.method == 'POST' and request.user.is_authenticated and request.user.is_staff and request.FILES.get('payment_proof'):
        q.payment_proof = request.FILES['payment_proof']
        q.save(update_fields=['payment_proof'])
        messages.success(request, 'Referencia de pago subida correctamente.')
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
            post_payment_statuses = {'pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado'}
            if os_ in post_payment_statuses and not q.payment_proof:
                messages.warning(request, 'Debe subir una referencia de pago antes de marcar este estado de pedido.')
            else:
                if q.order_status in post_payment_statuses and os_ not in post_payment_statuses:
                    messages.warning(request, 'No es posible regresar el estado del pedido una vez que ha sido marcado como pagado/enviado/recibido.')
                else:
                    # Si pasamos por primera vez a un estado post‑pago, descontar stock
                    previous_status = q.order_status
                    if os_ in post_payment_statuses and previous_status not in post_payment_statuses:
                        _deduct_stock_for_quotation(q)
                    q.order_status = os_
                    changed = True
        if changed:
            q.save(update_fields=['quotation_status', 'order_status', 'updated_at'])
            messages.success(request, 'Estados actualizados.')
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

    return render(
        request,
        'store/quotation_detail.html',
        {
            'quote': q,
            'items': items,
            'expires_at': expires_at,
            'total_base': total_base,
            'total_iva': total_iva,
        },
    )


def quotation_pdf(request, quotation_id):
    """Genera PDF de una cotización usando xhtml2pdf (si está instalado)."""
    q = get_object_or_404(Quotation.objects.select_related('existing_client', 'created_by'), id=quotation_id)
    items = q.items.select_related('product', 'product__category').all()
    expires_at = q.created_at + timedelta(days=1)

    try:
        from django.template.loader import get_template
        from xhtml2pdf import pisa
    except Exception:
        return HttpResponse('No está disponible la generación de PDF. Instala xhtml2pdf.', status=500)

    # Resolver rutas de static/media para xhtml2pdf
    from django.conf import settings
    from django.contrib.staticfiles import finders
    import os

    def link_callback(uri, rel):
        if uri.startswith(settings.MEDIA_URL):
            path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        elif uri.startswith(settings.STATIC_URL):
            path = finders.find(uri.replace(settings.STATIC_URL, ""))
        else:
            path = uri
        if not path:
            raise Exception(f'No se pudo resolver el recurso: {uri}')
        if isinstance(path, (list, tuple)):
            path = path[0]
        return path

    template = get_template('store/quotation_pdf.html')
    # Reusar mismos cálculos del detalle
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
            it.original_unit_price = it.product.price
            it.discount_unit = (it.original_unit_price - it.unit_price) if it.product.has_discount else Decimal('0.00')
        except Exception:
            it.original_unit_price = it.unit_price
            it.discount_unit = Decimal('0.00')
        total_base += it.base_subtotal
        total_iva += it.iva_subtotal

    html = template.render(
        {
            'quote': q,
            'items': items,
            'expires_at': expires_at,
            'total_base': total_base,
            'total_iva': total_iva,
        }
    )

    from io import BytesIO
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode('utf-8')),
        result,
        encoding='utf-8',
        link_callback=link_callback,
    )
    if pdf.err:
        return HttpResponse('Error generando el PDF.', status=500)

    # Nombre de archivo: COT{id}-FECHA-CLIENTE.pdf (cliente slugificado, sin espacios)
    from django.utils.text import slugify
    safe_client = slugify(q.client_name or 'sin-cliente')[:40]
    safe_date = q.created_at.strftime('%Y-%m-%d')
    filename = f"COT{q.id}-{safe_date}-{safe_client}.pdf"

    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    # inline: se abre en el navegador; el usuario puede imprimir o descargar desde ahí
    response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
    return response


@staff_member_required
def quotation_delete(request, quotation_id):
    """Eliminar una cotización (solo staff) con confirmación."""
    q = get_object_or_404(Quotation, id=quotation_id)
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
        f"Ubicación: {quote.client_departamento or '—'} - {quote.client_city or '—'}",
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
        from django.template.loader import get_template
        from xhtml2pdf import pisa
        from io import BytesIO
        from django.contrib.staticfiles import finders
        import os
        from django.utils.text import slugify

        items = quote.items.select_related('product', 'product__category').all()
        
        def link_callback(uri, rel):
            if uri.startswith(settings.MEDIA_URL):
                path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
            elif uri.startswith(settings.STATIC_URL):
                path = finders.find(uri.replace(settings.STATIC_URL, ""))
            else:
                path = uri
            if not path:
                raise Exception(f'No se pudo resolver el recurso: {uri}')
            if isinstance(path, (list, tuple)):
                path = path[0]
            return path

        template = get_template('store/quotation_pdf.html')
        
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
                it.original_unit_price = it.product.price
                it.discount_unit = (it.original_unit_price - it.unit_price) if it.product.has_discount else Decimal('0.00')
            except Exception:
                it.original_unit_price = it.unit_price
                it.discount_unit = Decimal('0.00')
            total_base += it.base_subtotal
            total_iva += it.iva_subtotal

        expires_at = quote.created_at + timedelta(days=1)
        html = template.render(
            {
                'quote': quote,
                'items': items,
                'expires_at': expires_at,
                'total_base': total_base,
                'total_iva': total_iva,
            }
        )

        result = BytesIO()
        pdf = pisa.pisaDocument(
            BytesIO(html.encode('utf-8')),
            result,
            encoding='utf-8',
            link_callback=link_callback,
        )
        if pdf.err:
            logger.warning("[TELEGRAM] Error generando PDF: %s", pdf.err)
            return

        pdf_bytes = result.getvalue()
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
                'document': (filename, pdf_bytes, 'application/pdf'),
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


def _get_quote_session(request) -> dict:
    """Return quotation session dict: {product_id(str): qty(int)}"""
    data = request.session.get('quotation', {})
    if not isinstance(data, dict):
        data = {}
    # sanitize
    clean: dict[str, int] = {}
    for k, v in data.items():
        try:
            pid = str(int(k))
            qty = int(v)
            if qty < 1:
                qty = 1
            clean[pid] = qty
        except (ValueError, TypeError):
            continue
    request.session['quotation'] = clean
    return clean


def _quote_payload(request) -> dict:
    """Build JSON payload for current quotation session."""
    q = _get_quote_session(request)
    ids = [int(pid) for pid in q.keys()]
    products = Product.objects.filter(id__in=ids).select_related('category')
    by_id = {p.id: p for p in products}
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

    for pid_str, qty in q.items():
        pid = int(pid_str)
        p = by_id.get(pid)
        if not p:
            continue
        unit = p.selling_price
        subtotal = unit * qty
        total += subtotal
        base_subtotal, iva_subtotal = split_iva(subtotal)
        base_unit, iva_unit = split_iva(unit)
        total_base += base_subtotal
        total_iva += iva_subtotal

        original_unit = p.price
        discount_unit = (original_unit - unit) if p.has_discount else Decimal('0.00')
        discount_total = discount_unit * qty
        items.append({
            'id': p.id,
            'name': p.name,
            'category': p.category.name,
            'image_url': p.image.url if p.image else '',
            'qty': qty,
            'unit_price': float(unit),
            'unit_base': float(base_unit),
            'unit_iva': float(iva_unit),
            'original_unit_price': float(original_unit),
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
    for pid in ids:
        try:
            pid_int = int(pid)
        except (ValueError, TypeError):
            continue
        if not Product.objects.filter(id=pid_int, available=True).exists():
            continue
        key = str(pid_int)
        if key not in q:
            q[key] = 1
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
    pid = request.POST.get('product_id')
    try:
        pid_int = int(pid)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid product_id'}, status=400)
    q.pop(str(pid_int), None)
    request.session['quotation'] = q
    request.session.modified = True
    return JsonResponse(_quote_payload(request))


def quotation_ajax_update_qty(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    q = _get_quote_session(request)
    pid = request.POST.get('product_id')
    qty = request.POST.get('qty')
    try:
        pid_int = int(pid)
        qty_int = int(qty)
        if qty_int < 1:
            qty_int = 1
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid data'}, status=400)
    key = str(pid_int)
    if key in q:
        q[key] = qty_int
        request.session['quotation'] = q
        request.session.modified = True
    return JsonResponse(_quote_payload(request))
