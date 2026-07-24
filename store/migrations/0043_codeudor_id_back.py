# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0042_rental_client_onboarding'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='codeudor_id_back',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='quotations/rental_requirements/ids/',
                verbose_name='Cédula del codeudor (reverso)',
            ),
        ),
    ]
