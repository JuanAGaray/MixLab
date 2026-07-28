"""
Cálculo de disponibilidad de alquiler considerando combos activos.

Las máquinas incluidas en combos disponibles no cuentan como stock libre
para alquiler individual en /rentals/.
"""
from collections import defaultdict

from django.db.models import Sum

from .models import QuotationItem, RentalComboItem

# Cotizaciones con estos estados AÚN NO comprometen la máquina en alquiler.
RENTAL_FREE_ORDER_STATUSES = {
    'sin_respuesta',
    'rechazado',
    'modificado_y_enviado',
}


def rental_committed_units_by_product() -> dict[int, int]:
    """Unidades comprometidas por cotizaciones de alquiler (por product_id)."""
    out_by_product: dict[int, int] = {}
    items = (
        QuotationItem.objects
        .filter(product__product_type='rental')
        .exclude(quotation__order_status__in=RENTAL_FREE_ORDER_STATUSES)
        .values_list('product_id', 'quantity')
    )
    for product_id, quantity in items:
        try:
            qty = int(quantity or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        out_by_product[product_id] = out_by_product.get(product_id, 0) + qty
    return out_by_product


def rental_combo_product_reserved() -> dict[int, int]:
    """Unidades reservadas por producto fijo en combos activos."""
    rows = (
        RentalComboItem.objects
        .filter(combo__available=True, product_id__isnull=False)
        .values('product_id')
        .annotate(qty=Sum('quantity'))
    )
    return {int(r['product_id']): int(r['qty'] or 0) for r in rows}


def rental_combo_category_reserved() -> dict[int, int]:
    """Unidades a tomar de una categoría (slots) en combos activos."""
    rows = (
        RentalComboItem.objects
        .filter(
            combo__available=True,
            category_id__isnull=False,
            product_id__isnull=True,
        )
        .values('category_id')
        .annotate(qty=Sum('quantity'))
    )
    return {int(r['category_id']): int(r['qty'] or 0) for r in rows}


def _product_base_available(product, out_by_product: dict, product_combo_reserved: dict) -> int:
    stock = int(product.stock or 0)
    out = int(out_by_product.get(product.id, 0))
    combo_fix = int(product_combo_reserved.get(product.id, 0))
    return max(0, stock - out - combo_fix)


def allocate_category_combo_reservations(
    rental_products,
    out_by_product: dict,
    product_combo_reserved: dict,
) -> dict[int, int]:
    """
    Asigna reservas de categoría a productos concretos (greedy por más stock libre).
    Retorna product_id -> unidades reservadas por slots de categoría en combos.
    """
    cat_reserved = rental_combo_category_reserved()
    if not cat_reserved:
        return {}

    products_by_cat: dict[int, list] = defaultdict(list)
    for p in rental_products:
        if p.category_id:
            products_by_cat[p.category_id].append(p)

    cat_alloc: dict[int, int] = {}
    for cat_id, reserve_qty in cat_reserved.items():
        remaining = int(reserve_qty or 0)
        if remaining <= 0:
            continue
        prods = products_by_cat.get(cat_id, [])
        prods_sorted = sorted(
            prods,
            key=lambda p: _product_base_available(p, out_by_product, product_combo_reserved),
            reverse=True,
        )
        for p in prods_sorted:
            if remaining <= 0:
                break
            base = _product_base_available(p, out_by_product, product_combo_reserved)
            take = min(base, remaining)
            if take > 0:
                cat_alloc[p.id] = cat_alloc.get(p.id, 0) + take
                remaining -= take
    return cat_alloc


def rental_effective_available(
    product,
    out_by_product: dict,
    product_combo_reserved: dict | None = None,
    category_alloc: dict | None = None,
) -> dict:
    """
    Disponibilidad efectiva de un producto de alquiler.

    Returns dict con stock, out, combo_fixed, combo_category, available.
    """
    product_combo_reserved = product_combo_reserved or rental_combo_product_reserved()
    category_alloc = category_alloc if category_alloc is not None else {}

    stock = int(product.stock or 0)
    out = int(out_by_product.get(product.id, 0))
    combo_fixed = int(product_combo_reserved.get(product.id, 0))
    combo_category = int(category_alloc.get(product.id, 0))
    available = max(0, stock - out - combo_fixed - combo_category)

    return {
        'stock': stock,
        'out': out,
        'combo_fixed': combo_fixed,
        'combo_category': combo_category,
        'combo_total': combo_fixed + combo_category,
        'available': available,
    }


def build_rental_availability_map(rental_products, out_by_product: dict) -> dict[int, dict]:
    """Mapa product_id -> métricas de disponibilidad para un listado de productos."""
    product_combo_reserved = rental_combo_product_reserved()
    category_alloc = allocate_category_combo_reservations(
        rental_products, out_by_product, product_combo_reserved,
    )
    result = {}
    for p in rental_products:
        result[p.id] = rental_effective_available(
            p, out_by_product, product_combo_reserved, category_alloc,
        )
    return result


def single_product_availability(product) -> dict:
    """Disponibilidad efectiva de un solo producto de alquiler."""
    from .models import Product

    out_by_product = rental_committed_units_by_product()
    product_combo_reserved = rental_combo_product_reserved()
    cat_reserved = rental_combo_category_reserved()

    rental_products = [product]
    if product.category_id and product.category_id in cat_reserved:
        rental_products = list(
            Product.objects.filter(
                product_type='rental',
                available=True,
                category_id=product.category_id,
            )
        )

    category_alloc = allocate_category_combo_reservations(
        rental_products, out_by_product, product_combo_reserved,
    )
    return rental_effective_available(
        product, out_by_product, product_combo_reserved, category_alloc,
    )
