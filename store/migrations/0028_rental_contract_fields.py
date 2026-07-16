from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0027_quotationitem_list_unit_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='rental_brand',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Marca'),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_model',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Modelo'),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_serial',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Número de serie'),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_commercial_value',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Referencia para indemnización por pérdida, hurto o daño total.',
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Valor comercial',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_condition',
            field=models.CharField(
                blank=True,
                default='Buen estado de funcionamiento',
                max_length=200,
                verbose_name='Estado del equipo',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_accessories',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Lista de accesorios (cables, tapas, bandejas, manuales, etc.).',
                verbose_name='Accesorios incluidos',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='rental_deposit',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Monto sugerido de depósito de garantía para el contrato.',
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Depósito / garantía',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='company_legal_name',
            field=models.CharField(
                blank=True,
                default='MixLab Alquiler e Insumos SAS',
                max_length=200,
                verbose_name='Razón social (arrendador)',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='company_nit',
            field=models.CharField(blank=True, default='', max_length=40, verbose_name='NIT del arrendador'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='company_address',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Dirección del arrendador'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='company_rep_name',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Representante legal'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='jurisdiction_city',
            field=models.CharField(
                blank=True,
                default='Cartagena',
                help_text='Ciudad cuyos jueces conocerán controversias del contrato.',
                max_length=100,
                verbose_name='Ciudad de jurisdicción',
            ),
        ),
        migrations.AddField(
            model_name='quotationitem',
            name='rental_price',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='quotation_items',
                to='store.productrentalprice',
                verbose_name='Tarifa de alquiler',
            ),
        ),
    ]
