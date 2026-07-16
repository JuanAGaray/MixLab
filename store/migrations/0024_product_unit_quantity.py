from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0023_product_unit_price'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='unit_price',
        ),
        migrations.AddField(
            model_name='product',
            name='unit_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text='Cantidad total del producto en la medida elegida (ej. 5 litros, 500 gr).',
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.001'))],
                verbose_name='Unidades totales',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='unit_price_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, se calcula el valor por medida (precio ÷ unidades totales).',
                verbose_name='Precio unitario',
            ),
        ),
    ]
