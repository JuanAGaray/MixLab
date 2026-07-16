from decimal import Decimal

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('store', '0033_delivery_acta_address_and_optional_gps'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='wa_n8n_enabled',
            field=models.BooleanField(default=True, verbose_name='Activar notificaciones WhatsApp (n8n)'),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='wa_n8n_phone',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Número de WhatsApp o ID de grupo que recibe las notificaciones automatizadas.',
                max_length=80,
                verbose_name='Teléfono o Group ID (n8n)',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='wa_n8n_webhook_url',
            field=models.URLField(
                blank=True,
                default='https://n8n.kodeuniverse.com/webhook/3348dc35-81fc-40cf-aae1-47f29e1caeb7',
                help_text='URL de producción del webhook n8n que envía mensajes a WhatsApp.',
                verbose_name='Webhook n8n (WhatsApp)',
            ),
        ),
        migrations.CreateModel(
            name='FinanceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('record_type', models.CharField(choices=[('gasto', 'Gasto'), ('pago', 'Pago')], max_length=20, verbose_name='Tipo')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Monto')),
                ('description', models.CharField(max_length=255, verbose_name='Descripción')),
                ('category', models.CharField(choices=[('operacion', 'Operación'), ('inventario', 'Inventario / insumos'), ('alquiler', 'Alquiler / local'), ('nomina', 'Nómina'), ('servicios', 'Servicios'), ('cliente', 'Pago de cliente'), ('proveedor', 'Pago a proveedor'), ('otro', 'Otro')], default='otro', max_length=30, verbose_name='Categoría')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Notas')),
                ('receipt', models.ImageField(blank=True, null=True, upload_to='finance/receipts/', verbose_name='Comprobante')),
                ('recorded_at', models.DateField(verbose_name='Fecha del movimiento')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_records', to='auth.user', verbose_name='Registrado por')),
                ('related_quotation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_records', to='store.quotation', verbose_name='Cotización relacionada')),
            ],
            options={
                'verbose_name': 'Gasto / Pago',
                'verbose_name_plural': 'Gastos y pagos',
                'ordering': ['-recorded_at', '-created_at'],
            },
        ),
    ]
