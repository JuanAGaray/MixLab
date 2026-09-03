from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0054_quotation_payment_cash_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='company_legal_rep_document',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Cédula del representante legal'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='company_legal_rep_name',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Representante legal (empresa)'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='company_nit',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='NIT de la empresa'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='conditions_accepted_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Condiciones aceptadas en'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='conditions_signature',
            field=models.ImageField(blank=True, null=True, upload_to='quotations/rental_requirements/signatures/', verbose_name='Firma de aceptación de condiciones'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='conditions_signer_document',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Documento quien acepta condiciones'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='conditions_signer_name',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Nombre quien acepta condiciones'),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='damage_terms_acknowledged',
            field=models.BooleanField(default=False, verbose_name='Aceptó tabla de daños y pérdidas'),
        ),
        migrations.CreateModel(
            name='RentalMachinePart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Parte / componente')),
                ('replacement_cost', models.DecimalField(decimal_places=2, help_text='Valor que debe pagar el arrendatario en caso de pérdida o daño irreparable.', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Costo de reposición')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(help_text='Producto de alquiler al que pertenece esta pieza.', on_delete=django.db.models.deletion.CASCADE, related_name='machine_parts', to='store.product', verbose_name='Máquina / producto')),
            ],
            options={
                'verbose_name': 'Parte de máquina',
                'verbose_name_plural': 'Partes de máquinas',
                'ordering': ['product_id', 'sort_order', 'name'],
            },
        ),
    ]
