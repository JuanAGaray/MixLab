from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0031_delivery_acta_location_video'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rentaldeliveryacta',
            name='reception_location',
            field=models.CharField(
                blank=True,
                default='',
                max_length=500,
                verbose_name='Lugar de recepción',
            ),
        ),
    ]
