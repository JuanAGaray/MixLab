from django.contrib import admin
from .models import Rental, RentalAvailability


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'product', 'status', 'start_date', 'end_date', 'total_price', 'created_at']
    list_filter = ['status', 'duration_type', 'created_at']
    search_fields = ['user__username', 'product__name', 'contact_name', 'contact_phone']
    readonly_fields = ['created_at', 'updated_at', 'total_price']
    
    fieldsets = (
        ('Información del Cliente', {
            'fields': ('user', 'status')
        }),
        ('Producto y Duración', {
            'fields': ('product', 'duration_type', 'duration_quantity', 'start_date', 'end_date')
        }),
        ('Precios', {
            'fields': ('daily_price', 'total_price')
        }),
        ('Información de Contacto', {
            'fields': ('contact_name', 'contact_phone', 'delivery_address', 'delivery_city', 'special_requirements')
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'completed_at')
        }),
    )


@admin.register(RentalAvailability)
class RentalAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['product', 'date', 'available', 'rental']
    list_filter = ['available', 'date', 'product']
    search_fields = ['product__name']

