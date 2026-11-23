from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0078_finance_payee_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='financerecord',
            name='accounting_book',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Movimiento creado en Contabilidad Mixlab, separado de cotizaciones.',
                verbose_name='Libro de contabilidad',
            ),
        ),
    ]
