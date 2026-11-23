from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0077_quotation_item_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='financerecord',
            name='payee',
            field=models.CharField(
                blank=True,
                default='',
                help_text='A quién se le pagó. Obligatorio en nómina.',
                max_length=160,
                verbose_name='Beneficiario',
            ),
        ),
        migrations.AddField(
            model_name='financerecord',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('efectivo', 'Efectivo'),
                    ('transferencia', 'Transferencia'),
                    ('nequi', 'Nequi'),
                    ('daviplata', 'Daviplata'),
                ],
                default='',
                max_length=20,
                verbose_name='Medio de pago',
            ),
        ),
    ]
