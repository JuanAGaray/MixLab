from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0044_access_password_plain'),
    ]

    operations = [
        migrations.CreateModel(
            name='RentalCombo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Nombre del combo')),
                ('slug', models.SlugField(unique=True, verbose_name='Slug')),
                ('description', models.TextField(blank=True, default='', verbose_name='Descripción')),
                ('image', models.ImageField(blank=True, null=True, upload_to='rental_combos/', verbose_name='Imagen')),
                ('for_events', models.BooleanField(default=True, help_text='Marca si este combo está pensado para alquiler de eventos.', verbose_name='Para eventos')),
                ('period_type', models.CharField(choices=[('event', 'Por evento'), ('daily', 'Por día'), ('hourly', 'Por hora'), ('weekly', 'Por semana')], default='event', max_length=20, verbose_name='Periodo del paquete')),
                ('package_price', models.DecimalField(blank=True, decimal_places=2, help_text='Si lo dejas vacío se usa la suma de los elementos. Si lo defines, es el precio cobrado del combo.', max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Precio del paquete')),
                ('available', models.BooleanField(default=True, verbose_name='Disponible')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Notas internas')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Combo de alquiler',
                'verbose_name_plural': 'Combos de alquiler',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RentalComboItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('custom_name', models.CharField(blank=True, default='', help_text='Para elementos que no están en inventario (mesas, decoración, personal, etc.).', max_length=200, verbose_name='Nombre del extra')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Cantidad')),
                ('unit_cost', models.DecimalField(decimal_places=2, help_text='Costo estipulado dentro del combo (puede sobrescribir el del inventario).', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Costo unitario')),
                ('notes', models.CharField(blank=True, default='', max_length=255, verbose_name='Notas')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('combo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='store.rentalcombo', verbose_name='Combo')),
                ('product', models.ForeignKey(blank=True, help_text='Si se elige, el costo puede tomarse de la tarifa del inventario.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='combo_usages', to='store.product', verbose_name='Producto de inventario')),
                ('rental_price', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='combo_usages', to='store.productrentalprice', verbose_name='Tarifa de alquiler')),
            ],
            options={
                'verbose_name': 'Elemento de combo',
                'verbose_name_plural': 'Elementos de combo',
                'ordering': ['order', 'id'],
            },
        ),
    ]
