from decimal import Decimal
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0020_promo_banner'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductRentalPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_type', models.CharField(
                    choices=[
                        ('hourly', 'Por hora'),
                        ('daily', 'Por día'),
                        ('weekly', 'Por semana'),
                        ('monthly', 'Por mes'),
                    ],
                    max_length=20,
                    verbose_name='Periodo',
                )),
                ('price', models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                    verbose_name='Precio',
                )),
                ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rental_prices',
                    to='store.product',
                    verbose_name='Producto',
                )),
            ],
            options={
                'verbose_name': 'Tarifa de alquiler',
                'verbose_name_plural': 'Tarifas de alquiler',
                'ordering': ['order', 'period_type'],
                'unique_together': {('product', 'period_type')},
            },
        ),
    ]
