from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0022_product_accent_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='unit_measure',
            field=models.CharField(
                blank=True,
                choices=[
                    ('oz', 'Onz'),
                    ('l', 'Litros'),
                    ('unit', 'Unidad'),
                    ('g', 'Gr'),
                    ('kg', 'Kilos'),
                ],
                default='l',
                max_length=10,
                verbose_name='Unidad de medida',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='unit_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                validators=[MinValueValidator(Decimal('0.01'))],
                verbose_name='Valor unitario',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='unit_price_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, se muestra el valor por unidad de medida.',
                verbose_name='Precio unitario',
            ),
        ),
    ]
