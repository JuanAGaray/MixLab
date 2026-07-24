from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal


class Category(models.Model):
    """Product categories"""
    name = models.CharField(max_length=100, verbose_name='Nombre')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    description = models.TextField(blank=True, verbose_name='Descripción')
    image = models.ImageField(upload_to='categories/', blank=True, null=True, verbose_name='Imagen')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """Products for sale or rental."""
    PRODUCT_TYPE_CHOICES = [
        ('sale', 'Venta'),
        ('rental', 'Alquiler'),
    ]

    name = models.CharField(max_length=200, verbose_name='Nombre')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    description = models.TextField(
        verbose_name='Descripción',
        help_text='Puedes usar formato de texto enriquecido: negrita, cursiva, listas, etc.'
    )
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products', verbose_name='Categoría')
    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        default='sale',
        verbose_name='Tipo'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Precio de Venta'
    )
    promotional_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Precio promocional (opcional). Si se establece, este será el precio mostrado.',
        verbose_name='Precio Promocional'
    )
    purchase_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Costo de compra del producto',
        verbose_name='Costo de Compra'
    )
    stock = models.PositiveIntegerField(default=0, verbose_name='Stock')
    available = models.BooleanField(default=True, verbose_name='Disponible')
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Imagen principal')
    keywords = models.CharField(
        max_length=500,
        blank=True,
        help_text='Separadas por comas. Ej: granizadora, hielo, bebida, frío',
        verbose_name='Palabras Clave'
    )
    accent_color = models.CharField(
        max_length=7,
        blank=True,
        default='',
        verbose_name='Color de diseño',
        help_text='Opcional. Hex (#0F6FFF). Se usa como fondo o acento en vitrinas y fichas del producto.',
    )
    UNIT_MEASURE_CHOICES = [
        ('oz', 'Onz'),
        ('l', 'Litros'),
        ('unit', 'Unidad'),
        ('g', 'Gr'),
        ('kg', 'Kilos'),
    ]
    unit_price_enabled = models.BooleanField(
        default=False,
        verbose_name='Precio unitario',
        help_text='Si está activo, se calcula el valor por medida (precio ÷ unidades totales).',
    )
    unit_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Unidades totales',
        help_text='Cantidad total del producto en la medida elegida (ej. 5 litros, 500 gr).',
    )
    unit_measure = models.CharField(
        max_length=10,
        choices=UNIT_MEASURE_CHOICES,
        blank=True,
        default='l',
        verbose_name='Unidad de medida',
    )
    related_products = models.ManyToManyField(
        'self',
        blank=True,
        help_text='Selecciona de 3 a 5 productos relacionados',
        limit_choices_to={'available': True},
        verbose_name='Productos Relacionados'
    )
    # Datos para contrato de alquiler (máquinas)
    rental_brand = models.CharField(max_length=120, blank=True, default='', verbose_name='Marca')
    rental_model = models.CharField(max_length=120, blank=True, default='', verbose_name='Modelo')
    rental_serial = models.CharField(max_length=120, blank=True, default='', verbose_name='Número de serie')
    rental_commercial_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Valor comercial',
        help_text='Referencia para indemnización por pérdida, hurto o daño total.',
    )
    rental_condition = models.CharField(
        max_length=200,
        blank=True,
        default='Buen estado de funcionamiento',
        verbose_name='Estado del equipo',
    )
    rental_accessories = models.TextField(
        blank=True,
        default='',
        verbose_name='Accesorios incluidos',
        help_text='Lista de accesorios (cables, tapas, bandejas, manuales, etc.).',
    )
    rental_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Depósito / garantía (opcional)',
        help_text='Opcional. Si el arrendador lo exige, el contrato aplica el 8% del valor comercial.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = self._ensure_valid_unique_slug()
        super().save(*args, **kwargs)

    def _ensure_valid_unique_slug(self) -> str:
        """Normaliza el slug (sin espacios) y evita colisiones."""
        import re

        base = slugify(self.slug or self.name) or slugify(self.name) or 'producto'
        # Defensa extra: solo caracteres válidos para la URL
        base = re.sub(r'[^a-zA-Z0-9_-]+', '-', base).strip('-_') or 'producto'
        slug = base
        qs = Product.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        counter = 1
        while qs.filter(slug=slug).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug

    @property
    def in_stock(self):
        return self.stock > 0
    
    @property
    def has_discount(self):
        """Check if product has promotional price"""
        return self.promotional_price is not None and self.promotional_price < self.price
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage"""
        if self.has_discount:
            return int(((self.price - self.promotional_price) / self.price) * 100)
        return 0

    @property
    def selling_price(self):
        """Price to use for display and cart: promotional if has_discount else price"""
        if self.has_discount:
            return self.promotional_price
        return self.price

    @property
    def has_unit_price(self):
        return bool(
            self.unit_price_enabled
            and self.unit_quantity
            and self.unit_quantity > 0
            and self.selling_price
        )

    @property
    def unit_measure_label(self):
        labels = {
            'oz': 'Onz',
            'l': 'Litros',
            'unit': 'Unidad',
            'g': 'Gr',
            'kg': 'Kilos',
        }
        return labels.get(self.unit_measure, self.get_unit_measure_display() if self.unit_measure else '')

    @property
    def unit_measure_singular(self):
        labels = {
            'oz': 'Onz',
            'l': 'Litro',
            'unit': 'Unidad',
            'g': 'Gr',
            'kg': 'Kilo',
        }
        return labels.get(self.unit_measure, self.unit_measure_label)

    @property
    def price_per_unit(self):
        """Precio de venta (u oferta) ÷ unidades totales."""
        if not self.has_unit_price:
            return None
        price = Decimal(str(self.selling_price))
        qty = Decimal(str(self.unit_quantity))
        if qty <= 0:
            return None
        return (price / qty).quantize(Decimal('0.01'))

    @property
    def unit_price_display_suffix(self):
        """Ej: /Litro, /Onz, /Unidad"""
        if not self.has_unit_price:
            return ''
        label = self.unit_measure_singular
        return f'/{label}' if label else ''

    @property
    def unit_quantity_display(self):
        """Ej: 5 Litros, 500 Gr"""
        if not self.unit_quantity:
            return ''
        qty = self.unit_quantity
        if qty == qty.to_integral_value():
            qty_str = str(int(qty))
        else:
            qty_str = format(qty.normalize(), 'f').rstrip('0').rstrip('.')
        label = self.unit_measure_label
        return f'{qty_str} {label}'.strip()

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.purchase_cost > 0:
            return float(((self.price - self.purchase_cost) / self.purchase_cost) * 100)
        return 0

    @property
    def is_rental(self):
        return self.product_type == 'rental'

    def get_rental_price(self, period_type):
        """Precio de alquiler para un periodo (hora, día, semana, mes)."""
        entry = self.rental_prices.filter(period_type=period_type, is_active=True).first()
        return entry.price if entry else None

    def sync_rental_catalog_price(self):
        """Sincroniza price base del catálogo desde tarifas de alquiler."""
        if not self.is_rental:
            return
        prices = self.rental_prices.filter(is_active=True).order_by('order', 'period_type')
        if not prices.exists():
            return
        preferred = prices.filter(period_type='daily').first() or prices.first()
        self.price = preferred.price
        self.purchase_cost = Decimal('0.00')
        self.promotional_price = None
        self.save(update_fields=['price', 'purchase_cost', 'promotional_price'])


class ProductRentalPrice(models.Model):
    """Tarifas de alquiler por periodo de tiempo."""

    PERIOD_CHOICES = [
        ('hourly', 'Por hora'),
        ('daily', 'Por día'),
        ('weekly', 'Por semana'),
        ('monthly', 'Por mes'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='rental_prices',
        verbose_name='Producto',
    )
    period_type = models.CharField(
        max_length=20,
        choices=PERIOD_CHOICES,
        verbose_name='Periodo',
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Precio',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tarifa de alquiler'
        verbose_name_plural = 'Tarifas de alquiler'
        ordering = ['order', 'period_type']
        unique_together = [['product', 'period_type']]

    def __str__(self):
        return f'{self.product.name} — {self.get_period_type_display()}: {self.price}'

    @property
    def period_short_label(self):
        labels = {
            'hourly': '/hora',
            'daily': '/día',
            'weekly': '/semana',
            'monthly': '/mes',
        }
        return labels.get(self.period_type, '')


class ProductImage(models.Model):
    """Additional images for products"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/', verbose_name='Imagen')
    alt_text = models.CharField(max_length=200, blank=True, verbose_name='Texto alternativo')
    is_primary = models.BooleanField(
        default=False,
        help_text='Marcar como imagen principal del producto',
        verbose_name='Imagen Principal'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imagen de Producto'
        verbose_name_plural = 'Imágenes de Productos'
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"Imagen de {self.product.name}"


class ProductVariation(models.Model):
    """Product variations (flavor, size, presentation, etc.)"""
    VARIATION_TYPE_CHOICES = [
        ('flavor', 'Sabor'),
        ('size', 'Tamaño'),
        ('presentation', 'Presentación'),
        ('other', 'Otro'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations', verbose_name='Producto')
    variation_type = models.CharField(
        max_length=20,
        choices=VARIATION_TYPE_CHOICES,
        default='other',
        verbose_name='Tipo de Variación'
    )
    name = models.CharField(
        max_length=100,
        help_text='Ej: Sabor, Tamaño, Presentación',
        verbose_name='Nombre de la Variación'
    )
    value = models.CharField(
        max_length=100,
        help_text='Ej: Fresa, Grande, Botella 500ml',
        verbose_name='Valor'
    )
    price_modifier = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Precio adicional (positivo) o descuento (negativo). Dejar en 0 para usar precio base.',
        verbose_name='Modificador de Precio'
    )
    stock = models.PositiveIntegerField(default=0, verbose_name='Stock')
    available = models.BooleanField(default=True, verbose_name='Disponible')
    sku = models.CharField(
        max_length=50,
        blank=True,
        unique=True,
        help_text='Código único del producto',
        verbose_name='SKU'
    )
    image = models.ImageField(upload_to='products/variations/', blank=True, null=True, verbose_name='Imagen')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Variación de Producto'
        verbose_name_plural = 'Variaciones de Productos'
        ordering = ['variation_type', 'value']
        unique_together = [['product', 'variation_type', 'value']]

    def __str__(self):
        return f"{self.product.name} - {self.name}: {self.value}"

    @property
    def final_price(self):
        """Calculate final price including modifier"""
        return self.product.price + self.price_modifier


class ProductVariationImage(models.Model):
    """Additional images for product variations"""
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE, related_name='images', verbose_name='Variación')
    image = models.ImageField(upload_to='products/variations/', verbose_name='Imagen')
    alt_text = models.CharField(max_length=200, blank=True, verbose_name='Texto alternativo')
    is_primary = models.BooleanField(
        default=False,
        help_text='Marcar como imagen principal de la variación',
        verbose_name='Imagen Principal'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imagen de Variación'
        verbose_name_plural = 'Imágenes de Variaciones'
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"Imagen de {self.variation}"


class ProductTechnicalSpec(models.Model):
    """Flexible technical specifications for products"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='technical_specs', verbose_name='Producto')
    name = models.CharField(
        max_length=200,
        help_text='Ej: Tipo de Empaque, Duración, Peso, Dimensiones, etc.',
        verbose_name='Nombre de la Característica'
    )
    description = models.CharField(
        max_length=500,
        help_text='Ej: Bolsa, 12 meses, 500g, 20x15x10 cm, etc.',
        verbose_name='Descripción/Valor'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text='Orden de visualización (menor número aparece primero)',
        verbose_name='Orden'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Especificación Técnica'
        verbose_name_plural = 'Especificaciones Técnicas'
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.product.name} - {self.name}: {self.description}"


class ProductAttribute(models.Model):
    """Flexible attributes for products (warranty, size, etc.)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes', verbose_name='Producto')
    key = models.CharField(
        max_length=100,
        help_text='Ej: Garantía, Tamaño, Peso, Dimensiones, Material, etc.',
        verbose_name='Atributo'
    )
    value = models.CharField(
        max_length=500,
        help_text='Ej: 12 meses, Grande, 500g, 20x15x10 cm, Plástico, etc.',
        verbose_name='Valor'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text='Orden de visualización (menor número aparece primero)',
        verbose_name='Orden'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Atributo de Producto'
        verbose_name_plural = 'Atributos de Productos'
        ordering = ['order', 'key']
        unique_together = [['product', 'key']]

    def __str__(self):
        return f"{self.product.name} - {self.key}: {self.value}"


class Cart(models.Model):
    """Shopping cart"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart', verbose_name='Usuario')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Carrito'
        verbose_name_plural = 'Carritos'

    def __str__(self):
        return f"Carrito de {self.user.username}"

    @property
    def item_count(self):
        """Total number of items in cart"""
        return sum(item.quantity for item in self.items.all())

    @property
    def total(self):
        """Total price of all items in cart"""
        return sum(item.subtotal for item in self.items.all())


class CartItem(models.Model):
    """Items in shopping cart"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', verbose_name='Carrito')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Producto')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name='Cantidad')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item de Carrito'
        verbose_name_plural = 'Items de Carrito'
        unique_together = [['cart', 'product']]

    def __str__(self):
        return f"{self.quantity}x {self.product.name} en {self.cart}"

    @property
    def subtotal(self):
        """Calculate subtotal for this item (uses selling_price: promotional when applicable)"""
        return self.product.selling_price * self.quantity


class Order(models.Model):
    """Customer orders"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
        ('preparing', 'En preparación'),
        ('shipped', 'Enviado'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders', verbose_name='Usuario')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Estado')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Total')
    shipping_address = models.TextField(verbose_name='Dirección de envío')
    shipping_city = models.CharField(max_length=100, verbose_name='Ciudad')
    shipping_phone = models.CharField(max_length=20, verbose_name='Teléfono')
    shipping_notes = models.TextField(blank=True, verbose_name='Notas de envío')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-created_at']

    def __str__(self):
        return f"Pedido #{self.id} de {self.user.username}"


class OrderItem(models.Model):
    """Items in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Pedido')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Producto')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Cantidad')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio unitario')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Item de Pedido'
        verbose_name_plural = 'Items de Pedido'

    def __str__(self):
        return f"{self.quantity}x {self.product.name} en pedido #{self.order.id}"

    @property
    def subtotal(self):
        """Calculate subtotal for this item"""
        return self.price * self.quantity


class Quotation(models.Model):
    """Customer quotation (cotización)"""

    CLIENT_KIND_CHOICES = [
        ('existing', 'Cliente existente'),
        ('natural', 'Persona natural'),
        ('empresa', 'Empresa'),
    ]

    QUOTATION_STATUS_CHOICES = [
        ('generada', 'Generada'),
        ('enviada', 'Enviada'),
        ('cerrada', 'Cerrada'),
        ('vencida', 'Vencida'),
        ('cancelada', 'Cancelada'),
    ]

    ORDER_STATUS_CHOICES = [
        ('sin_respuesta', 'Sin respuesta'),
        ('aceptado', 'Aceptado'),
        ('esperando_pago', 'Esperando pago'),
        ('pago_parcial', 'Pago parcial'),
        ('pago_recibido', 'Pago recibido'),
        ('enviado', 'Enviado'),
        ('recibido', 'Recibido'),
        ('rechazado', 'Rechazado'),
        ('modificado_y_enviado', 'Modificado y enviado'),
    ]

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_quotations',
        verbose_name='Creado por',
    )
    existing_client = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations',
        verbose_name='Cliente existente',
    )
    client_kind = models.CharField(max_length=20, choices=CLIENT_KIND_CHOICES, default='existing', verbose_name='Tipo de cliente')

    client_name = models.CharField(max_length=200, blank=True, verbose_name='Nombre/Razón social')
    client_email = models.EmailField(blank=True, verbose_name='Correo')
    client_phone = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    client_document = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='Número de cédula / documento',
    )
    client_departamento = models.CharField(max_length=100, blank=True, verbose_name='Departamento')
    client_city = models.CharField(max_length=100, blank=True, verbose_name='Ciudad')

    notes = models.TextField(blank=True, verbose_name='Notas')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Total')

    quotation_status = models.CharField(
        max_length=20,
        choices=QUOTATION_STATUS_CHOICES,
        default='generada',
        verbose_name='Estado de la cotización',
    )
    order_status = models.CharField(
        max_length=30,
        choices=ORDER_STATUS_CHOICES,
        default='sin_respuesta',
        verbose_name='Estado del pedido',
    )
    payment_proof = models.ImageField(
        upload_to='quotations/payment_proofs/',
        blank=True,
        null=True,
        verbose_name='Referencia de pago',
    )
    partial_payment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Monto de pago parcial',
        help_text='Abono registrado cuando el estado es pago parcial.',
    )
    stock_deducted = models.BooleanField(
        default=False,
        verbose_name='Stock descontado',
        help_text='Indica si el inventario de esta cotización ya fue restado.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f'Cotización #{self.id}'

    @property
    def has_rental_items(self) -> bool:
        return self.items.filter(product__product_type='rental').exists()

    @property
    def amount_paid(self) -> Decimal:
        """Monto abonado: parcial registrado o total si ya está pagado completo."""
        if self.order_status in ('pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado'):
            return Decimal(str(self.total or 0))
        if self.partial_payment_amount is not None:
            return Decimal(str(self.partial_payment_amount))
        return Decimal('0.00')

    @property
    def remaining_balance(self) -> Decimal:
        """Saldo pendiente por pagar."""
        total = Decimal(str(self.total or 0))
        paid = self.amount_paid
        remaining = total - paid
        return remaining if remaining > 0 else Decimal('0.00')

    def _linked_client_profile(self):
        """Perfil del cliente existente vinculado, si existe."""
        if not self.existing_client_id:
            return None
        try:
            return self.existing_client.profile
        except Exception:
            return None

    def sync_client_snapshot_from_profile(self, *, save: bool = True) -> bool:
        """
        Sincroniza datos del cliente existente vinculado.
        Nombre/correo/teléfono se toman siempre del usuario/perfil actual.
        Departamento/ciudad se rellenan si la cotización los tiene vacíos.
        """
        if not self.existing_client_id:
            return False

        client = self.existing_client
        profile = self._linked_client_profile()
        changed_fields = []

        live_name = (client.get_full_name() or client.username or '').strip()
        if live_name and (self.client_name or '').strip() != live_name:
            self.client_name = live_name
            changed_fields.append('client_name')

        live_email = (client.email or '').strip()
        if live_email and (self.client_email or '').strip() != live_email:
            self.client_email = live_email
            changed_fields.append('client_email')

        if profile:
            profile_type = (getattr(profile, 'client_type', '') or '').strip()
            if self.client_kind in ('', 'existing') and profile_type in ('natural', 'empresa'):
                self.client_kind = profile_type
                changed_fields.append('client_kind')

            live_phone = (getattr(profile, 'phone', '') or '').strip()
            if live_phone and (self.client_phone or '').strip() != live_phone:
                self.client_phone = live_phone
                changed_fields.append('client_phone')

            live_document = (getattr(profile, 'document_number', '') or '').strip()
            if live_document and (self.client_document or '').strip() != live_document:
                self.client_document = live_document
                changed_fields.append('client_document')

            profile_depto = (getattr(profile, 'departamento', '') or '').strip()
            profile_city = (getattr(profile, 'city', '') or '').strip()
            if (not profile_depto or not profile_city) and getattr(profile, 'default_shipping_address_id', None):
                addr = profile.default_shipping_address
                if addr:
                    profile_depto = profile_depto or (addr.departamento or '').strip()
                    profile_city = profile_city or (addr.city or '').strip()

            if profile_depto and (self.client_departamento or '').strip() != profile_depto:
                self.client_departamento = profile_depto
                changed_fields.append('client_departamento')
            if profile_city and (self.client_city or '').strip() != profile_city:
                self.client_city = profile_city
                changed_fields.append('client_city')

        if changed_fields and save:
            changed_fields.append('updated_at')
            self.save(update_fields=list(dict.fromkeys(changed_fields)))
        return bool(changed_fields)

    @property
    def display_client_name(self) -> str:
        """Nombre actual del cliente vinculado, o el guardado en la cotización."""
        if self.existing_client_id:
            try:
                name = (self.existing_client.get_full_name() or self.existing_client.username or '').strip()
                if name:
                    return name
            except Exception:
                pass
        return (self.client_name or '').strip()

    @property
    def display_client_email(self) -> str:
        if self.existing_client_id:
            try:
                email = (self.existing_client.email or '').strip()
                if email:
                    return email
            except Exception:
                pass
        return (self.client_email or '').strip()

    @property
    def display_client_phone(self) -> str:
        profile = self._linked_client_profile()
        if profile and (profile.phone or '').strip():
            return profile.phone.strip()
        return (self.client_phone or '').strip()

    @property
    def display_client_document(self) -> str:
        profile = self._linked_client_profile()
        if profile and (getattr(profile, 'document_number', '') or '').strip():
            return profile.document_number.strip()
        return (self.client_document or '').strip()

    @property
    def display_client_kind(self) -> str:
        """Etiqueta amigable del tipo de cliente (Persona natural / Empresa)."""
        kind = (self.client_kind or '').strip()
        if kind in ('natural', 'empresa'):
            return dict(self.CLIENT_KIND_CHOICES).get(kind, kind)
        profile = self._linked_client_profile()
        if profile and (profile.client_type or '') in ('natural', 'empresa'):
            return profile.get_client_type_display()
        return self.get_client_kind_display()

    @property
    def display_client_departamento(self) -> str:
        profile = self._linked_client_profile()
        if profile and (profile.departamento or '').strip():
            return profile.departamento.strip()
        return (self.client_departamento or '').strip()

    @property
    def display_client_city(self) -> str:
        profile = self._linked_client_profile()
        if profile and (profile.city or '').strip():
            return profile.city.strip()
        return (self.client_city or '').strip()


class QuotationItem(models.Model):
    """Line items for a quotation"""

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items', verbose_name='Cotización')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='quotation_items', verbose_name='Producto')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Cantidad')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Precio unitario')
    list_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio lista unitario',
        help_text='Precio de catálogo/tarifa antes del descuento de la línea.',
    )
    rental_price = models.ForeignKey(
        'ProductRentalPrice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotation_items',
        verbose_name='Tarifa de alquiler',
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Subtotal')

    class Meta:
        verbose_name = 'Item de Cotización'
        verbose_name_plural = 'Items de Cotización'

    def __str__(self):
        return f'{self.quantity}x {self.product.name} (Cotización #{self.quotation_id})'

    def save(self, *args, **kwargs):
        self.subtotal = (self.unit_price or Decimal('0.00')) * (self.quantity or 1)
        super().save(*args, **kwargs)


class RentalContractRequirements(models.Model):
    """Requisitos previos al contrato: firmas digitales, fotos de cédula y onboarding del cliente."""

    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.CASCADE,
        related_name='rental_requirements',
        verbose_name='Cotización',
    )
    representative_name = models.CharField(max_length=200, blank=True, default='', verbose_name='Nombre representante')
    representative_signature = models.ImageField(
        upload_to='quotations/rental_requirements/signatures/',
        blank=True,
        null=True,
        verbose_name='Firma del representante',
    )
    tenant_name = models.CharField(max_length=200, blank=True, default='', verbose_name='Nombre arrendatario')
    tenant_signature = models.ImageField(
        upload_to='quotations/rental_requirements/signatures/',
        blank=True,
        null=True,
        verbose_name='Firma del arrendatario',
    )
    id_front = models.ImageField(
        upload_to='quotations/rental_requirements/ids/',
        blank=True,
        null=True,
        verbose_name='Cédula (frente)',
    )
    id_back = models.ImageField(
        upload_to='quotations/rental_requirements/ids/',
        blank=True,
        null=True,
        verbose_name='Cédula (reverso)',
    )
    selfie_with_id = models.ImageField(
        upload_to='quotations/rental_requirements/ids/',
        blank=True,
        null=True,
        verbose_name='Selfie con cédula al lado del rostro',
    )
    location_text = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Ubicación manual / dirección',
    )
    maps_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Enlace Google Maps',
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name='Latitud',
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name='Longitud',
    )
    codeudor_required = models.BooleanField(
        default=False,
        verbose_name='Requiere codeudor',
        help_text='Si está activo, el cliente debe registrar datos del codeudor en el formulario móvil.',
    )
    codeudor_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Nombre completo del codeudor',
    )
    codeudor_document = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='Cédula / documento del codeudor',
    )
    codeudor_id_front = models.ImageField(
        upload_to='quotations/rental_requirements/ids/',
        blank=True,
        null=True,
        verbose_name='Cédula del codeudor (frente)',
    )
    access_token = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        verbose_name='Token de acceso cliente',
    )
    access_password_hash = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name='Hash de contraseña de acceso',
    )
    link_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Enlace expira en',
    )
    client_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cliente envió datos en',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Notas')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Completado en')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Requisitos de contrato de alquiler'
        verbose_name_plural = 'Requisitos de contratos de alquiler'

    def __str__(self):
        return f'Requisitos COT-{self.quotation_id}'

    @property
    def is_complete(self) -> bool:
        return bool(
            self.representative_signature
            and self.tenant_signature
            and self.id_front
            and self.id_back
            and self.quotation.display_client_document
            and self.quotation.display_client_email
            and self.quotation.display_client_phone
        )

    @property
    def client_onboarding_complete(self) -> bool:
        """Datos mínimos que el cliente remite desde el celular."""
        base_ok = bool(
            (self.tenant_name or '').strip()
            and self.id_front
            and self.id_back
            and self.selfie_with_id
            and ((self.location_text or '').strip() or (self.maps_url or '').strip())
        )
        if not base_ok:
            return False
        if self.codeudor_required:
            return bool(
                (self.codeudor_name or '').strip()
                and (self.codeudor_document or '').strip()
                and self.codeudor_id_front
            )
        return True

    @property
    def link_is_active(self) -> bool:
        if not self.access_token or not self.access_password_hash:
            return False
        if self.link_expires_at and timezone.now() > self.link_expires_at:
            return False
        return True



class RentalDeliveryActa(models.Model):
    """Acta de recepción/entrega del equipo con firmas y fotos del estado."""

    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.CASCADE,
        related_name='delivery_acta',
        verbose_name='Cotización',
    )
    representative_name = models.CharField(max_length=200, blank=True, default='', verbose_name='Nombre representante')
    representative_signature = models.ImageField(
        upload_to='quotations/delivery_acta/signatures/',
        blank=True,
        null=True,
        verbose_name='Firma del representante',
    )
    tenant_name = models.CharField(max_length=200, blank=True, default='', verbose_name='Nombre arrendatario')
    tenant_signature = models.ImageField(
        upload_to='quotations/delivery_acta/signatures/',
        blank=True,
        null=True,
        verbose_name='Firma del arrendatario',
    )
    photo_covers = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Tapas y plásticos',
    )
    photo_lighting = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Iluminación',
    )
    photo_buttons = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Botones',
    )
    photo_radiator = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Radiador',
    )
    photo_rear = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Parte trasera',
    )
    photo_front = models.ImageField(
        upload_to='quotations/delivery_acta/photos/',
        blank=True,
        null=True,
        verbose_name='Parte delantera',
    )
    reception_location = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Dirección de recepción',
        help_text='Dirección escrita del lugar donde se entrega/recibe el equipo.',
    )
    reception_maps_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Ubicación GPS (Google Maps)',
        help_text='Opcional. Enlace de Google Maps con la ubicación GPS.',
    )
    reception_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name='Latitud',
    )
    reception_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name='Longitud',
    )
    delivery_video = models.FileField(
        upload_to='quotations/delivery_acta/videos/',
        blank=True,
        null=True,
        verbose_name='Video de recepción',
    )
    delivery_notes = models.TextField(blank=True, default='', verbose_name='Observaciones de entrega')
    delivered_at = models.DateTimeField(blank=True, null=True, verbose_name='Fecha de entrega')
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name='Completado en')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Acta de recepción de alquiler'
        verbose_name_plural = 'Actas de recepción de alquiler'

    def __str__(self):
        return f'Acta recepción COT-{self.quotation_id}'

    @property
    def is_complete(self) -> bool:
        return bool(
            (self.representative_name or '').strip()
            and self.representative_signature
            and (self.tenant_name or '').strip()
            and self.tenant_signature
            and (self.reception_location or '').strip()
            and self.delivery_video
            and self.photo_covers
            and self.photo_lighting
            and self.photo_buttons
            and self.photo_radiator
            and self.photo_rear
            and self.photo_front
        )

    def photo_items(self):
        """Lista de fotos etiquetadas para formularios/PDF."""
        return [
            ('photo_covers', 'Tapas y plásticos', self.photo_covers),
            ('photo_lighting', 'Iluminación', self.photo_lighting),
            ('photo_buttons', 'Botones', self.photo_buttons),
            ('photo_radiator', 'Radiador', self.photo_radiator),
            ('photo_rear', 'Parte trasera', self.photo_rear),
            ('photo_front', 'Parte delantera', self.photo_front),
        ]


class FavoriteProduct(models.Model):
    """Productos guardados en favoritos por usuario."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_products', verbose_name='Usuario')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by', verbose_name='Producto')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Favorito'
        verbose_name_plural = 'Favoritos'
        unique_together = [['user', 'product']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} ❤️ {self.product.name}"


class DilutionBaseProduct(models.Model):
    """Producto base para la calculadora de dilución con agua (ML)."""

    name = models.CharField(max_length=200, verbose_name='Nombre')
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        verbose_name='Enlace para compartir',
        help_text='Se genera automáticamente. Ej: base-granizado → /calculadora/#base-granizado',
    )
    description = models.TextField(
        blank=True,
        verbose_name='Descripción / instrucciones',
        help_text='Opcional: notas de preparación para mostrar en la calculadora.',
    )
    water_ml_per_base_ml = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='ML de agua por cada 1 ML de producto base',
        help_text='Ejemplo: proporción 1:4 → ingresa 4 (por cada 1 ml de base, 4 ml de agua).',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Producto base (calculadora)'
        verbose_name_plural = 'Productos base (calculadora)'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> str:
        base = slugify(self.name) or 'producto'
        slug = base
        counter = 1
        qs = DilutionBaseProduct.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        while qs.filter(slug=slug).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug

    @property
    def ratio_display(self) -> str:
        w = self.water_ml_per_base_ml
        if w == w.to_integral_value():
            return f'1 : {int(w)}'
        return f'1 : {w}'

    def calculate_water_ml(self, base_ml: Decimal) -> Decimal:
        base = base_ml if isinstance(base_ml, Decimal) else Decimal(str(base_ml))
        return (base * self.water_ml_per_base_ml).quantize(Decimal('0.01'))

    def calculate_total_ml(self, base_ml: Decimal) -> Decimal:
        base = base_ml if isinstance(base_ml, Decimal) else Decimal(str(base_ml))
        return (base + self.calculate_water_ml(base)).quantize(Decimal('0.01'))


class SiteSettings(models.Model):
    """Configuración global del sitio (singleton): contacto, redes y banner."""

    contact_email = models.EmailField(
        default='juandam594@gmail.com',
        verbose_name='Correo de contacto',
    )
    contact_phone = models.CharField(
        max_length=30,
        default='3128104046',
        verbose_name='Teléfono (visualización)',
    )
    whatsapp_number = models.CharField(
        max_length=20,
        default='573128104046',
        verbose_name='WhatsApp (solo dígitos con código país)',
        help_text='Ej: 573045379501 — se usa para el botón flotante y enlaces wa.me',
    )
    wa_n8n_webhook_url = models.URLField(
        blank=True,
        default='https://n8n.kodeuniverse.com/webhook/3348dc35-81fc-40cf-aae1-47f29e1caeb7',
        verbose_name='Webhook n8n (WhatsApp)',
        help_text='URL de producción del webhook n8n que envía mensajes a WhatsApp.',
    )
    wa_n8n_phone = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Teléfono o Group ID (n8n)',
        help_text='Número de WhatsApp o ID de grupo que recibe las notificaciones automatizadas.',
    )
    wa_n8n_enabled = models.BooleanField(
        default=True,
        verbose_name='Activar notificaciones WhatsApp (n8n)',
    )
    address_city = models.CharField(
        max_length=100,
        default='Cartagena',
        verbose_name='Ciudad',
    )
    address_country = models.CharField(
        max_length=100,
        default='Colombia',
        verbose_name='País',
    )
    instagram_url = models.URLField(
        blank=True,
        default='https://www.instagram.com/mixlab_co',
        verbose_name='URL de Instagram',
    )
    tiktok_url = models.URLField(
        blank=True,
        default='https://www.tiktok.com/@mixlab_co',
        verbose_name='URL de TikTok',
    )
    facebook_url = models.URLField(blank=True, verbose_name='URL de Facebook')
    # Datos legales para contratos de alquiler (Registro Mercantil)
    company_legal_name = models.CharField(
        max_length=200,
        blank=True,
        default='MIXLAB SAS',
        verbose_name='Razón social (arrendador)',
    )
    company_nit = models.CharField(
        max_length=40,
        blank=True,
        default='902031074-1',
        verbose_name='NIT del arrendador',
    )
    company_address = models.CharField(
        max_length=255,
        blank=True,
        default='Barrio Ciudad Bicentenario, Conjunto Residencial Parques de Bolívar 2',
        verbose_name='Dirección del arrendador',
    )
    company_department = models.CharField(
        max_length=100,
        blank=True,
        default='Bolívar',
        verbose_name='Departamento',
    )
    company_matricula = models.CharField(
        max_length=40,
        blank=True,
        default='10006865',
        verbose_name='Matrícula mercantil',
        help_text='Número de matrícula en Cámara de Comercio.',
    )
    company_rep_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Representante legal',
    )
    jurisdiction_city = models.CharField(
        max_length=100,
        blank=True,
        default='Cartagena',
        verbose_name='Ciudad de jurisdicción',
        help_text='Ciudad cuyos jueces conocerán controversias del contrato.',
    )
    promo_banner_text = models.CharField(
        max_length=300,
        blank=True,
        default='',
        verbose_name='Texto del banner promocional',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración del sitio'
        verbose_name_plural = 'Configuración del sitio'

    def __str__(self):
        return 'Configuración del sitio'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def display_address(self) -> str:
        return f'{self.address_city}, {self.address_country}'

    @property
    def whatsapp_url(self) -> str:
        import re
        digits = re.sub(r'\D', '', self.whatsapp_number or '')
        return f'https://wa.me/{digits}' if digits else ''

    @property
    def social_links(self) -> list:
        links = []
        if self.instagram_url:
            links.append(self.instagram_url)
        if self.tiktok_url:
            links.append(self.tiktok_url)
        if self.facebook_url:
            links.append(self.facebook_url)
        return links


class FinanceRecord(models.Model):
    """Registro de gastos y pagos (caja) con notificación opcional a WhatsApp."""

    TYPE_CHOICES = [
        ('gasto', 'Gasto'),
        ('pago', 'Pago'),
    ]
    CATEGORY_CHOICES = [
        ('operacion', 'Operación'),
        ('inventario', 'Inventario / insumos'),
        ('alquiler', 'Alquiler / local'),
        ('nomina', 'Nómina'),
        ('servicios', 'Servicios'),
        ('cliente', 'Pago de cliente'),
        ('proveedor', 'Pago a proveedor'),
        ('otro', 'Otro'),
    ]

    record_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name='Tipo',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Monto',
    )
    description = models.CharField(max_length=255, verbose_name='Descripción')
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default='otro',
        verbose_name='Categoría',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Notas')
    receipt = models.ImageField(
        upload_to='finance/receipts/',
        blank=True,
        null=True,
        verbose_name='Comprobante',
    )
    related_quotation = models.ForeignKey(
        Quotation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_records',
        verbose_name='Cotización relacionada',
    )
    recorded_at = models.DateField(verbose_name='Fecha del movimiento')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finance_records',
        verbose_name='Registrado por',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Gasto / Pago'
        verbose_name_plural = 'Gastos y pagos'
        ordering = ['-recorded_at', '-created_at']

    def __str__(self):
        return f'{self.get_record_type_display()} · {self.amount} · {self.description}'


class PaymentMethod(models.Model):
    """Métodos de pago configurables (bancos / cuentas) para cotizaciones y sitio."""

    ACCOUNT_TYPE_CHOICES = [
        ('ahorros', 'Ahorros'),
        ('corriente', 'Corriente'),
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
        ('otro', 'Otro'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('cc', 'C.C.'),
        ('nit', 'NIT'),
        ('ce', 'C.E.'),
        ('otro', 'Otro'),
    ]

    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='ahorros',
        verbose_name='Tipo de cuenta',
    )
    bank_name = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Banco / entidad',
        help_text='Ej: Bancolombia S.A.',
    )
    bank_logo = models.ImageField(
        upload_to='payment_methods/',
        blank=True,
        null=True,
        verbose_name='Logo del banco',
    )
    holder_name = models.CharField(
        max_length=200,
        verbose_name='A nombre de',
    )
    document_type = models.CharField(
        max_length=10,
        choices=DOCUMENT_TYPE_CHOICES,
        default='cc',
        verbose_name='Tipo doc.',
    )
    document_number = models.CharField(
        max_length=40,
        verbose_name='NIT o C.C.',
    )
    account_number = models.CharField(
        max_length=60,
        verbose_name='Número de cuenta',
    )
    breb_key = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Llave BREB (opcional)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Método de pago'
        verbose_name_plural = 'Métodos de pago'
        ordering = ['sort_order', 'id']

    def __str__(self):
        bank = self.bank_name or self.get_account_type_display()
        return f'{bank} · {self.account_number}'

    @property
    def document_display(self) -> str:
        return f'{self.get_document_type_display()} {self.document_number}'.strip()


class SidebarBanner(models.Model):
    """Publicidad en banner lateral del sitio (proporción 2:3)."""

    title = models.CharField(
        max_length=120,
        verbose_name='Título (interno)',
        help_text='Solo para identificarlo en el panel de administración.',
    )
    image = models.ImageField(
        upload_to='banners/sidebar/',
        verbose_name='Imagen',
        help_text='Proporción 2:3 (ancho:alto). Se guarda en Supabase (bucket Mixlaba).',
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Texto alternativo',
        help_text='Descripción breve de la imagen para accesibilidad.',
    )
    link_url = models.URLField(
        blank=True,
        verbose_name='Enlace (opcional)',
        help_text='Si se indica, la imagen será clicable.',
    )
    open_in_new_tab = models.BooleanField(
        default=True,
        verbose_name='Abrir enlace en nueva pestaña',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Banner lateral'
        verbose_name_plural = 'Banners laterales'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return self.title


class PromoBanner(models.Model):
    """Imágenes del banner promocional superior del sitio."""

    title = models.CharField(
        max_length=120,
        verbose_name='Título (interno)',
        help_text='Solo para identificarlo en el panel de administración.',
    )
    image = models.ImageField(
        upload_to='promo-banners/',
        verbose_name='Imagen',
        help_text='Banner ancho superior. Se guarda en Supabase (bucket Mixlaba).',
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Texto alternativo',
    )
    link_url = models.URLField(
        blank=True,
        verbose_name='Enlace (opcional)',
    )
    open_in_new_tab = models.BooleanField(
        default=True,
        verbose_name='Abrir enlace en nueva pestaña',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Banner promocional'
        verbose_name_plural = 'Banners promocionales'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return self.title


class DrinzzContractConfig(models.Model):
    """
    Contrato marco de colaboración operativa Drinzz (singleton).
    Editable por admin: términos comerciales y cláusulas adicionales.
    """

    operator_brand = models.CharField(
        max_length=120,
        default='Drinzz',
        verbose_name='Marca del operador',
    )
    operator_legal_name = models.CharField(
        max_length=200,
        blank=True,
        default='MIXLAB SAS',
        verbose_name='Razón social del operador',
        help_text='Persona jurídica que opera/representa el modelo Drinzz.',
    )
    operator_nit = models.CharField(
        max_length=40,
        blank=True,
        default='902031074-1',
        verbose_name='NIT del operador',
    )
    operator_address = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Dirección del operador',
    )
    operator_city = models.CharField(
        max_length=100,
        blank=True,
        default='Cartagena',
        verbose_name='Ciudad del operador',
    )
    operator_rep_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Representante legal del operador',
    )
    associate_pct = models.PositiveIntegerField(
        default=30,
        verbose_name='% utilidades asociado (meta facturación)',
        help_text='Porcentaje del asociado cuando la facturación mensual supera el umbral.',
    )
    operator_pct = models.PositiveIntegerField(
        default=70,
        verbose_name='% utilidades operador (meta facturación)',
        help_text='Porcentaje del operador cuando la facturación mensual supera el umbral.',
    )
    associate_pct_month1 = models.PositiveIntegerField(
        default=20,
        verbose_name='% utilidades asociado (primer mes)',
    )
    operator_pct_month1 = models.PositiveIntegerField(
        default=80,
        verbose_name='% utilidades operador (primer mes)',
    )
    billing_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('6000000.00'),
        verbose_name='Umbral de facturación mensual (COP)',
        help_text='Facturación mensual a partir de la cual aplica el reparto 30/70.',
    )
    maintain_bonus_pct = models.PositiveIntegerField(
        default=10,
        verbose_name='% bonificación por mantener meta',
        help_text='Si se mantiene facturación sobre el umbral en meses siguientes, la liquidación del asociado sube este porcentaje.',
    )
    expenses_assumed = models.TextField(
        default='Luz (consumo eléctrico del punto), insumos (bases, vasos, tapas y consumibles) y alquiler conforme al esquema del punto.',
        verbose_name='Gastos asumidos por el operador',
    )
    provides_operators = models.BooleanField(
        default=True,
        verbose_name='El operador puede colocar personal operador',
    )
    estimated_income_min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('500000.00'),
        verbose_name='Ingreso estimado mínimo asociado (COP)',
    )
    estimated_income_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('3500000.00'),
        verbose_name='Ingreso estimado máximo asociado (COP)',
    )
    contract_duration_months = models.PositiveIntegerField(
        default=12,
        verbose_name='Duración inicial (meses)',
    )
    renewal_auto = models.BooleanField(
        default=True,
        verbose_name='Renovación automática',
    )
    termination_notice_days = models.PositiveIntegerField(
        default=30,
        verbose_name='Días de preaviso para terminación',
    )
    settlement_days = models.PositiveIntegerField(
        default=10,
        verbose_name='Días hábiles para liquidación de utilidades',
        help_text='Plazo para liquidar y pagar utilidades del periodo.',
    )
    jurisdiction_city = models.CharField(
        max_length=100,
        default='Cartagena',
        verbose_name='Ciudad de jurisdicción',
    )
    object_clause = models.TextField(
        verbose_name='Cláusula de objeto',
        default=(
            'El presente contrato tiene por objeto establecer una colaboración operativa '
            'para la instalación, puesta en marcha y explotación de un punto de venta de '
            'granizados (bebidas congeladas) dentro de un local comercial del ASOCIADO, '
            'bajo la marca y modelo operativo Drinzz. El OPERADOR aporta la infraestructura, '
            'insumos y operación; el ASOCIADO aporta el espacio físico y el flujo de clientes '
            'del establecimiento.'
        ),
    )
    associate_obligations = models.TextField(
        verbose_name='Obligaciones del asociado',
        default=(
            '1) Facilitar un espacio adecuado, seguro y visible dentro del local para el punto.\n'
            '2) Permitir el acceso del OPERADOR y su personal para instalación, reposición, '
            'mantenimiento y operación.\n'
            '3) No interferir en la operación diaria ni en la calidad del producto.\n'
            '4) Informar de inmediato cualquier daño, hurto, falla o incidente.\n'
            '5) Abstenerse de comercializar productos competidores de granizados en el mismo '
            'espacio durante la vigencia, salvo autorización escrita del OPERADOR.'
        ),
    )
    operator_obligations = models.TextField(
        verbose_name='Obligaciones del operador',
        default=(
            '1) Instalar y mantener la infraestructura del punto de granizados.\n'
            '2) Asumir los gastos de luz, insumos y alquiler conforme al esquema pactado.\n'
            '3) Proveer operadores cuando se acuerde para la atención del punto.\n'
            '4) Reponer insumos y garantizar continuidad operativa razonable.\n'
            '5) Registrar compras, gastos y ventas del punto de forma automatizada en Biztra, '
            'garantizando transparencia total en la información operativa y financiera.\n'
            '6) Liquidar utilidades en los plazos acordados con base en los registros del sistema.'
        ),
    )
    transparency_clause = models.TextField(
        verbose_name='Cláusula de transparencia (Biztra)',
        default=(
            'Todas las compras, gastos y ventas del punto se registrarán de manera automatizada '
            'a través de la plataforma Biztra, con el fin de garantizar total transparencia '
            'frente al ASOCIADO. El ASOCIADO podrá conocer, conforme a los accesos y reportes '
            'habilitados, la información de ventas, costos y liquidaciones del punto. '
            'Las partes reconocen que Biztra es la fuente operativa de registro para efectos '
            'de control, seguimiento y liquidación de utilidades.'
        ),
        help_text='Se incluye en el contrato PDF y en la página de alianza.',
    )
    additional_clauses = models.TextField(
        blank=True,
        default='',
        verbose_name='Cláusulas adicionales (editables)',
        help_text='Texto libre que se insertará al final del contrato, antes de firmas. Una cláusula por párrafo.',
    )
    disclaimer_income = models.TextField(
        verbose_name='Aviso sobre ingresos estimados',
        default=(
            'Las cifras de ingreso estimado del ASOCIADO son referenciales, basadas en la '
            'experiencia de puntos en operación, y no constituyen garantía ni promesa de '
            'resultados. El rendimiento real depende de ubicación, flujo de clientes, '
            'horarios, temporada y demás factores del mercado.'
        ),
    )
    version_label = models.CharField(
        max_length=40,
        default='v1.0',
        verbose_name='Versión del contrato',
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name='Publicar descarga en la página de alianza',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Contrato Drinzz'
        verbose_name_plural = 'Contrato Drinzz'

    def __str__(self):
        return f'Contrato Drinzz {self.version_label}'

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.associate_pct is not None and (int(self.associate_pct) + int(self.operator_pct or 0)) != 100:
            self.operator_pct = max(0, 100 - int(self.associate_pct))
        if self.associate_pct_month1 is not None and (
            int(self.associate_pct_month1) + int(self.operator_pct_month1 or 0)
        ) != 100:
            self.operator_pct_month1 = max(0, 100 - int(self.associate_pct_month1))
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
