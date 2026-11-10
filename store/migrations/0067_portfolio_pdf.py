from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0066_service_review_bonus'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='portfolio_pdf',
            field=models.FileField(
                blank=True,
                help_text='PDF para compartir con clientes en la web.',
                null=True,
                upload_to='portfolio/',
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf'])],
                verbose_name='Portafolio PDF',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='portfolio_title',
            field=models.CharField(
                blank=True,
                default='Portafolio de productos MixLab',
                max_length=200,
                verbose_name='Título del portafolio',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='portfolio_updated_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Portafolio actualizado en',
            ),
        ),
    ]
