from django.contrib import admin
from django.db.models import Count, Sum
from django.utils.html import format_html
from store.models import Order, Product, Category
from rentals.models import Rental


class FrozzAdminSite(admin.AdminSite):
    site_header = "Frozz - Panel de Administración"
    site_title = "Frozz Admin"
    index_title = "Bienvenido al Panel de Administración"


admin_site = FrozzAdminSite(name='frozz_admin')


@admin.register(Order, site=admin_site)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'total', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'user__email']


@admin.register(Product, site=admin_site)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'product_type', 'price', 'stock', 'available']


@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']


@admin.register(Rental, site=admin_site)
class RentalAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'product', 'status', 'start_date', 'end_date', 'total_price']


# Customize default admin
admin.site.site_header = "Frozz - Panel de Administración"
admin.site.site_title = "Frozz Admin"
admin.site.index_title = "Bienvenido al Panel de Administración"

