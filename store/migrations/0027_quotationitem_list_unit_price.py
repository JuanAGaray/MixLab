from decimal import Decimal

from django.db import migrations, models


def backfill_list_unit_prices(apps, schema_editor):
    QuotationItem = apps.get_model('store', 'QuotationItem')
    ProductRentalPrice = apps.get_model('store', 'ProductRentalPrice')

    for item in QuotationItem.objects.select_related('product').iterator():
        product = item.product
        unit = item.unit_price or Decimal('0.00')
        list_price = None

        if getattr(product, 'product_type', '') == 'rental':
            tariffs = list(
                ProductRentalPrice.objects.filter(
                    product_id=product.id,
                    is_active=True,
                ).values_list('price', flat=True)
            )
            if tariffs:
                above = [t for t in tariffs if t >= unit]
                list_price = min(above) if above else max(tariffs)

        if list_price is None:
            list_price = product.price or unit

        if list_price < unit:
            list_price = unit

        item.list_unit_price = list_price
        item.save(update_fields=['list_unit_price'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0026_paymentmethod'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationitem',
            name='list_unit_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Precio de catálogo/tarifa antes del descuento de la línea.',
                max_digits=12,
                null=True,
                verbose_name='Precio lista unitario',
            ),
        ),
        migrations.RunPython(backfill_list_unit_prices, noop_reverse),
    ]
