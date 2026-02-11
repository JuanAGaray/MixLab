from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal
from store.models import Product


class Rental(models.Model):
    """Machine rental orders"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('confirmed', 'Confirmado'),
        ('active', 'Activo'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado'),
    ]

    DURATION_CHOICES = [
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rentals', verbose_name='Usuario')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='rentals', verbose_name='Producto')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Estado')
    duration_type = models.CharField(max_length=20, choices=DURATION_CHOICES, verbose_name='Tipo de duración')
    duration_quantity = models.PositiveIntegerField(default=1, verbose_name='Cantidad de duración')
    
    # Dates
    start_date = models.DateField(verbose_name='Fecha de inicio')
    end_date = models.DateField(verbose_name='Fecha de fin')
    
    # Pricing
    daily_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio diario')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio total')
    
    # Contact information
    contact_name = models.CharField(max_length=200, verbose_name='Nombre de contacto')
    contact_phone = models.CharField(max_length=20, verbose_name='Teléfono de contacto')
    delivery_address = models.TextField(verbose_name='Dirección de entrega')
    delivery_city = models.CharField(max_length=100, verbose_name='Ciudad de entrega')
    special_requirements = models.TextField(blank=True, verbose_name='Requisitos especiales')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Alquiler'
        verbose_name_plural = 'Alquileres'
        ordering = ['-created_at']

    def __str__(self):
        return f"Alquiler #{self.id} - {self.product.name} - {self.user.username}"

    def calculate_total(self):
        """Calculate rental total based on duration"""
        from datetime import timedelta
        days = (self.end_date - self.start_date).days + 1
        
        if self.duration_type == 'daily':
            return self.daily_price * days
        elif self.duration_type == 'weekly':
            weeks = (days + 6) // 7  # Round up
            return self.daily_price * 7 * weeks * 0.85  # 15% discount for weekly
        elif self.duration_type == 'monthly':
            months = max(1, days // 30)
            return self.daily_price * 30 * months * 0.75  # 25% discount for monthly
        
        return self.daily_price * days


class RentalAvailability(models.Model):
    """Track rental availability calendar"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='availability', verbose_name='Producto')
    date = models.DateField(verbose_name='Fecha')
    available = models.BooleanField(default=True, verbose_name='Disponible')
    rental = models.ForeignKey(Rental, on_delete=models.SET_NULL, null=True, blank=True, related_name='availability_dates', verbose_name='Alquiler')

    class Meta:
        verbose_name = 'Disponibilidad de Alquiler'
        verbose_name_plural = 'Disponibilidades de Alquiler'
        unique_together = ['product', 'date']
        ordering = ['date']

    def __str__(self):
        return f"{self.product.name} - {self.date}"

