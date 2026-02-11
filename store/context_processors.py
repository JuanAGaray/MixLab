from .models import Cart, Category


def cart(request):
    """Add cart to context"""
    if request.user.is_authenticated:
        cart_obj, created = Cart.objects.get_or_create(user=request.user)
        return {
            'cart': cart_obj,
            'cart_item_count': cart_obj.item_count,
            'cart_total': cart_obj.total,
            'session_cart_items': None,
        }
    # Anonymous: cart from session so floating button + offcanvas work everywhere
    from decimal import Decimal
    from .models import Product
    session_cart = request.session.get('cart', {})
    cart_item_count = sum(session_cart.values()) if isinstance(session_cart, dict) else 0
    cart_items = []
    cart_total = Decimal('0.00')
    if isinstance(session_cart, dict) and session_cart:
        # Bulk-fetch products to keep it fast
        ids = []
        for pid_str in session_cart.keys():
            try:
                ids.append(int(pid_str))
            except (TypeError, ValueError):
                continue
        products_by_id = Product.objects.filter(id__in=ids, available=True).in_bulk()

        class TempCartItem:
            def __init__(self, product, quantity):
                self.product = product
                self.quantity = quantity
                self.id = product.id  # for update/remove endpoints in session mode

            @property
            def subtotal(self):
                return self.product.selling_price * self.quantity

        for pid_str, qty in session_cart.items():
            try:
                pid = int(pid_str)
                q = int(qty)
            except (TypeError, ValueError):
                continue
            product = products_by_id.get(pid)
            if not product or q <= 0:
                continue
            item = TempCartItem(product, q)
            cart_items.append(item)
            cart_total += item.subtotal
    return {
        'cart': None,
        'cart_item_count': cart_item_count,
        'cart_total': cart_total,
        'session_cart_items': cart_items,
    }


def categories(request):
    """Add categories to context"""
    return {
        'categories': Category.objects.all().order_by('name'),
    }

