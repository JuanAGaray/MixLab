from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0055_rental_machine_parts_and_conditions'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='company_tax_regime',
            field=models.CharField(
                blank=True,
                default='Régimen común',
                help_text='Ej: Régimen común, Régimen simple de tributación.',
                max_length=80,
                verbose_name='Régimen tributario',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='cuenta_cobro_ica_per_mille',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('9.6600'),
                help_text='Tarifa de retención de ICA por mil sobre la base (referencia municipal).',
                max_digits=8,
                verbose_name='ICA cuenta de cobro (‰)',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='cuenta_cobro_payment_days',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='0 = contado. Ej: 15 o 30 días para fecha máxima de pago.',
                verbose_name='Plazo cuenta de cobro (días)',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='dian_invoice_resolution',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Número de resolución autorizada por la DIAN para factura electrónica.',
                max_length=120,
                verbose_name='Resolución facturación electrónica DIAN',
            ),
        ),
    ]
