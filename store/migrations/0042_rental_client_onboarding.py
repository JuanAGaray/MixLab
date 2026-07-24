# Generated manually for client rental onboarding link

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0041_drinzz_biztra_transparency'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='selfie_with_id',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='quotations/rental_requirements/ids/',
                verbose_name='Selfie con cédula al lado del rostro',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='location_text',
            field=models.CharField(
                blank=True,
                default='',
                max_length=500,
                verbose_name='Ubicación manual / dirección',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='maps_url',
            field=models.URLField(
                blank=True,
                default='',
                max_length=500,
                verbose_name='Enlace Google Maps',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
                verbose_name='Latitud',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
                verbose_name='Longitud',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='codeudor_required',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, el cliente debe registrar datos del codeudor en el formulario móvil.',
                verbose_name='Requiere codeudor',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='codeudor_name',
            field=models.CharField(
                blank=True,
                default='',
                max_length=200,
                verbose_name='Nombre completo del codeudor',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='codeudor_document',
            field=models.CharField(
                blank=True,
                default='',
                max_length=30,
                verbose_name='Cédula / documento del codeudor',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='codeudor_id_front',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='quotations/rental_requirements/ids/',
                verbose_name='Cédula del codeudor (frente)',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='access_token',
            field=models.UUIDField(
                blank=True,
                db_index=True,
                null=True,
                unique=True,
                verbose_name='Token de acceso cliente',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='access_password_hash',
            field=models.CharField(
                blank=True,
                default='',
                max_length=128,
                verbose_name='Hash de contraseña de acceso',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='link_expires_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Enlace expira en',
            ),
        ),
        migrations.AddField(
            model_name='rentalcontractrequirements',
            name='client_submitted_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Cliente envió datos en',
            ),
        ),
    ]
