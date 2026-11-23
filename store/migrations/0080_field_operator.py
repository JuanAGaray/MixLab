from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0079_finance_accounting_book'),
    ]

    operations = [
        migrations.CreateModel(
            name='FieldOperator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Nombre')),
                ('phone', models.CharField(blank=True, default='', max_length=40, verbose_name='Teléfono')),
                ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Operario',
                'verbose_name_plural': 'Operarios',
                'ordering': ['name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='combobooking',
            name='operator',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bookings',
                to='store.fieldoperator',
                verbose_name='Operario',
            ),
        ),
        migrations.AddField(
            model_name='combobooking',
            name='operator_arrival',
            field=models.TimeField(blank=True, null=True, verbose_name='Hora de llegada del operario'),
        ),
    ]
