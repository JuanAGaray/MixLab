from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0037_quotation_client_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='partial_payment_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Abono registrado cuando el estado es pago parcial.',
                max_digits=12,
                null=True,
                validators=[MinValueValidator(Decimal('0.01'))],
                verbose_name='Monto de pago parcial',
            ),
        ),
    ]
