from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('normatividad/', views.normatividad, name='normatividad'),
    path('products/', views.product_list, name='product_list'),
    path('products/<slug:slug>/', views.product_detail, name='product_detail'),
    path('calculadora/', views.water_calculator, name='water_calculator'),
    path('cart/', views.cart, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/guest/', views.guest_checkout, name='guest_checkout'),
    path('checkout/guest/login/', views.guest_checkout_login, name='guest_checkout_login'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('favorites/toggle/<int:product_id>/', views.favorite_toggle, name='favorite_toggle'),
    path('cotizacion/', views.quotation, name='quotation'),
    path('cotizaciones/', views.quotation_list, name='quotation_list'),
    path('cotizaciones/ajax/set-status/', views.quotation_ajax_set_status, name='quotation_ajax_set_status'),
    path('cotizaciones/<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('cotizaciones/<int:quotation_id>/pdf/', views.quotation_pdf, name='quotation_pdf'),
    path('cotizaciones/<int:quotation_id>/pdf/file/', views.quotation_pdf_file, name='quotation_pdf_file'),
    path('cotizaciones/<int:quotation_id>/factura/', views.quotation_invoice_download, name='quotation_invoice_download'),
    path('cotizaciones/<int:quotation_id>/contrato-alquiler/', views.quotation_rental_contract, name='quotation_rental_contract'),
    path('cotizaciones/<int:quotation_id>/requisitos-contrato/', views.quotation_rental_requirements, name='quotation_rental_requirements'),
    path('cotizaciones/<int:quotation_id>/acta-recepcion/', views.quotation_delivery_acta, name='quotation_delivery_acta'),
    path('cotizaciones/<int:quotation_id>/acta-recepcion/pdf/', views.quotation_delivery_acta_pdf, name='quotation_delivery_acta_pdf'),
    path('cotizaciones/ajax/reverse-geocode/', views.ajax_reverse_geocode, name='ajax_reverse_geocode'),
    path('cotizaciones/<int:quotation_id>/eliminar/', views.quotation_delete, name='quotation_delete'),
    path('cotizacion/ajax/add/', views.quotation_ajax_add, name='quotation_ajax_add'),
    path('cotizacion/ajax/remove/', views.quotation_ajax_remove, name='quotation_ajax_remove'),
    path('cotizacion/ajax/update-qty/', views.quotation_ajax_update_qty, name='quotation_ajax_update_qty'),
    path('cotizacion/ajax/update-discount/', views.quotation_ajax_update_discount, name='quotation_ajax_update_discount'),
    
    # Manager - Clientes
    path('manager/clientes/', views.client_list, name='client_list'),
    path('manager/clientes/crear/', views.client_create, name='client_create'),
    path('manager/clientes/<int:client_id>/', views.client_detail, name='client_detail'),
    path('manager/clientes/<int:client_id>/editar/', views.client_edit, name='client_edit'),
    path('manager/clientes/<int:client_id>/eliminar/', views.client_delete, name='client_delete'),
    path('manager/clientes/<int:client_id>/generar-password/', views.client_generate_password, name='client_generate_password'),

    # Manager - Personal (vendedores / admins)
    path('manager/personal/', views.staff_user_list, name='staff_user_list'),
    path('manager/personal/crear/', views.staff_user_create, name='staff_user_create'),
    path('manager/personal/<int:user_id>/editar/', views.staff_user_edit, name='staff_user_edit'),
    path('manager/personal/<int:user_id>/desactivar/', views.staff_user_toggle_active, name='staff_user_toggle_active'),

    # Manager - Ventas
    path('manager/ventas/', views.sales_list, name='sales_list'),

    # Manager - Gastos y pagos
    path('manager/finanzas/', views.finance_list, name='finance_list'),
    path('manager/finanzas/<int:record_id>/eliminar/', views.finance_delete, name='finance_delete'),
    
    # Inventory routes
    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    path('inventory/products/', views.inventory_list, name='inventory_list'),
    path('inventory/products/create/', views.inventory_create, name='inventory_create'),
    path('inventory/products/<int:product_id>/', views.inventory_detail, name='inventory_detail'),
    path('inventory/products/<int:product_id>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/products/<int:product_id>/delete/', views.inventory_delete, name='inventory_delete'),
    path('inventory/products/<int:product_id>/duplicate/', views.inventory_duplicate, name='inventory_duplicate'),
    path('inventory/products/<int:product_id>/toggle-available/', views.inventory_toggle_available, name='inventory_toggle_available'),
    
    # Product images
    path('inventory/products/<int:product_id>/add-image/', views.inventory_add_image, name='inventory_add_image'),
    path('inventory/products/<int:product_id>/delete-image/<int:image_id>/', views.inventory_delete_image, name='inventory_delete_image'),
    
    # Product variations
    path('inventory/products/<int:product_id>/add-variation/', views.inventory_add_variation, name='inventory_add_variation'),
    path('inventory/products/<int:product_id>/edit-variation/<int:variation_id>/', views.inventory_edit_variation, name='inventory_edit_variation'),
    path('inventory/products/<int:product_id>/delete-variation/<int:variation_id>/', views.inventory_delete_variation, name='inventory_delete_variation'),
    
    # Variation images
    path('inventory/products/<int:product_id>/variation/<int:variation_id>/add-image/', views.inventory_add_variation_image, name='inventory_add_variation_image'),
    path('inventory/products/<int:product_id>/variation/<int:variation_id>/delete-image/<int:image_id>/', views.inventory_delete_variation_image, name='inventory_delete_variation_image'),
    
    # Technical specs
    path('inventory/products/<int:product_id>/add-spec/', views.inventory_add_technical_spec, name='inventory_add_technical_spec'),
    path('inventory/products/<int:product_id>/edit-spec/<int:spec_id>/', views.inventory_edit_technical_spec, name='inventory_edit_technical_spec'),
    path('inventory/products/<int:product_id>/delete-spec/<int:spec_id>/', views.inventory_delete_technical_spec, name='inventory_delete_technical_spec'),
    
    # Product attributes
    path('inventory/products/<int:product_id>/add-attribute/', views.inventory_add_attribute, name='inventory_add_attribute'),
    path('inventory/products/<int:product_id>/edit-attribute/<int:attribute_id>/', views.inventory_edit_attribute, name='inventory_edit_attribute'),
    path('inventory/products/<int:product_id>/delete-attribute/<int:attribute_id>/', views.inventory_delete_attribute, name='inventory_delete_attribute'),
    
    # Categories
    path('inventory/categories/create/', views.inventory_create_category, name='inventory_create_category'),

    # Calculadora de dilución (admin)
    path('inventory/calculadora/', views.dilution_product_list, name='dilution_product_list'),
    path('inventory/calculadora/nuevo/', views.dilution_product_create, name='dilution_product_create'),
    path('inventory/calculadora/<int:item_id>/editar/', views.dilution_product_edit, name='dilution_product_edit'),
    path('inventory/calculadora/<int:item_id>/eliminar/', views.dilution_product_delete, name='dilution_product_delete'),

    # Configuración del sitio (contacto, redes, WA)
    path('inventory/configuracion-sitio/', views.site_settings_edit, name='site_settings_edit'),
]
