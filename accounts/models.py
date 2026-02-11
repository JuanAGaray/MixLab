from django.db import models
from django.contrib.auth.models import User


class ShippingAddress(models.Model):
    """Shipping addresses for users (DPA Colombia: departamento, ciudad, dirección exacta, referencia, Google Maps)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_addresses')
    departamento = models.CharField(max_length=100, default='', verbose_name='Departamento')
    city = models.CharField(max_length=100, verbose_name='Ciudad')
    address = models.TextField(verbose_name='Dirección exacta')
    punto_referencia = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Punto de referencia',
        help_text='Ej: Frente al parque, diagonal a la panadería'
    )
    google_maps_ubicacion = models.URLField(
        max_length=500,
        blank=True,
        verbose_name='Ubicación en Google Maps',
        help_text='Pega el enlace de Google Maps de la ubicación'
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')
    is_default = models.BooleanField(default=False, verbose_name='Dirección Predeterminada')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dirección de Envío'
        verbose_name_plural = 'Direcciones de Envío'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        parts = [self.address, self.city]
        if self.departamento:
            parts.append(self.departamento)
        return ", ".join(parts)

    def as_text(self):
        """Texto completo para envío (ej. en pedidos)."""
        parts = [self.departamento, self.city, self.address]
        if self.punto_referencia:
            parts.append(f"Ref: {self.punto_referencia}")
        return " | ".join(parts)

    def save(self, *args, **kwargs):
        # If this is set as default, unset other defaults for this user
        if self.is_default:
            ShippingAddress.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    """Extended user profile"""
    CLIENT_TYPE_CHOICES = [
        ('natural', 'Persona natural'),
        ('empresa', 'Empresa'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')  # Stores comma-separated phones
    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default='natural',
        blank=True,
        verbose_name='Tipo de cliente',
    )
    departamento = models.CharField(max_length=100, blank=True, default='', verbose_name='Departamento')
    city = models.CharField(max_length=100, blank=True, default='', verbose_name='Ciudad')
    address = models.TextField(blank=True, verbose_name='Dirección')
    birth_date = models.DateField(null=True, blank=True, verbose_name='Fecha de nacimiento')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Avatar')
    default_shipping_address = models.ForeignKey(
        'ShippingAddress',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_for_profiles',
        verbose_name='Dirección de Envío Predeterminada'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f"Perfil de {self.user.username}"
