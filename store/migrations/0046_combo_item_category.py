from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0045_rental_combo'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcomboitem',
            name='category',
            field=models.ForeignKey(
                blank=True,
                help_text='Al confirmar el pedido se toma un producto disponible de esta categoría.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='combo_usages',
                to='store.category',
                verbose_name='Categoría (slot)',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcomboitem',
            name='product',
            field=models.ForeignKey(
                blank=True,
                help_text='Producto fijo. El costo se toma del costo de compra.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='combo_usages',
                to='store.product',
                verbose_name='Producto de inventario',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcomboitem',
            name='unit_cost',
            field=models.DecimalField(
                decimal_places=2,
                help_text='Costo de compra / costo estipulado (no el precio de venta).',
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Costo unitario',
            ),
        ),
    ]
