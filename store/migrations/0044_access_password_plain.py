from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0043_codeudor_id_back'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='access_password',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Se muestra al staff para reenviar al cliente. El hash se usa para validar.',
                max_length=32,
                verbose_name='Contraseña de acceso (texto claro para staff)',
            ),
        ),
    ]
