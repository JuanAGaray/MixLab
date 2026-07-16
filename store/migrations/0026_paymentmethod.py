from django.db import migrations, models


def seed_default_payment_method(apps, schema_editor):
    PaymentMethod = apps.get_model('store', 'PaymentMethod')
    if PaymentMethod.objects.exists():
        return
    PaymentMethod.objects.create(
        account_type='ahorros',
        bank_name='Bancolombia S.A.',
        holder_name='MixLab',
        document_type='cc',
        document_number='1143397396',
        account_number='912-097121-60',
        breb_key='1143397396',
        is_active=True,
        sort_order=0,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0025_quotation_stock_deducted'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('account_type', models.CharField(choices=[('ahorros', 'Ahorros'), ('corriente', 'Corriente'), ('nequi', 'Nequi'), ('daviplata', 'Daviplata'), ('otro', 'Otro')], default='ahorros', max_length=20, verbose_name='Tipo de cuenta')),
                ('bank_name', models.CharField(blank=True, default='', help_text='Ej: Bancolombia S.A.', max_length=120, verbose_name='Banco / entidad')),
                ('bank_logo', models.ImageField(blank=True, null=True, upload_to='payment_methods/', verbose_name='Logo del banco')),
                ('holder_name', models.CharField(max_length=200, verbose_name='A nombre de')),
                ('document_type', models.CharField(choices=[('cc', 'C.C.'), ('nit', 'NIT'), ('ce', 'C.E.'), ('otro', 'Otro')], default='cc', max_length=10, verbose_name='Tipo doc.')),
                ('document_number', models.CharField(max_length=40, verbose_name='NIT o C.C.')),
                ('account_number', models.CharField(max_length=60, verbose_name='Número de cuenta')),
                ('breb_key', models.CharField(blank=True, default='', max_length=80, verbose_name='Llave BREB (opcional)')),
                ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Método de pago',
                'verbose_name_plural': 'Métodos de pago',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_default_payment_method, noop_reverse),
    ]
