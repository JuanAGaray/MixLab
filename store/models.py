from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.text import slugify
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
    """Products for sale, rental, supplies, and disposables"""
    PRODUCT_TYPE_CHOICES = [
        ('sale', 'Venta'),
        ('rental', 'Alquiler'),
        ('supply', 'Insumo'),
        ('disposable', 'Desechable'),
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
    related_products = models.ManyToManyField(
        'self',
        blank=True,
        help_text='Selecciona de 3 a 5 productos relacionados',
        limit_choices_to={'available': True},
        verbose_name='Productos Relacionados'
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
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

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
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.purchase_cost > 0:
            return float(((self.price - self.purchase_cost) / self.purchase_cost) * 100)
        return 0


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
        ('vencida', 'Vencida'),
        ('cancelada', 'Cancelada'),
    ]

    ORDER_STATUS_CHOICES = [
        ('sin_respuesta', 'Sin respuesta'),
        ('aceptado', 'Aceptado'),
        ('esperando_pago', 'Esperando pago'),
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f'Cotización #{self.id}'


class QuotationItem(models.Model):
    """Line items for a quotation"""

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items', verbose_name='Cotización')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='quotation_items', verbose_name='Producto')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name='Cantidad')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Precio unitario')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Subtotal')

    class Meta:
        verbose_name = 'Item de Cotización'
        verbose_name_plural = 'Items de Cotización'

    def __str__(self):
        return f'{self.quantity}x {self.product.name} (Cotización #{self.quotation_id})'

    def save(self, *args, **kwargs):
        self.subtotal = (self.unit_price or Decimal('0.00')) * (self.quantity or 1)
        super().save(*args, **kwargs)


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
