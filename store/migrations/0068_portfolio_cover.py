from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0067_portfolio_pdf'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='portfolio_cover',
            field=models.ImageField(
                blank=True,
                help_text='Imagen de vista previa (WhatsApp, redes). Ideal 1200×630 px, JPG o PNG.',
                null=True,
                upload_to='portfolio/covers/',
                verbose_name='Miniatura al compartir',
            ),
        ),
    ]
