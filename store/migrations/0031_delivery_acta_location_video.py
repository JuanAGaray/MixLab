from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0030_rental_requirements_delivery_acta'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentaldeliveryacta',
            name='delivery_video',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='quotations/delivery_acta/videos/',
                verbose_name='Video de recepción',
            ),
        ),
        migrations.AddField(
            model_name='rentaldeliveryacta',
            name='reception_location',
            field=models.CharField(
                blank=True,
                default='',
                max_length=300,
                verbose_name='Lugar de recepción',
            ),
        ),
    ]
