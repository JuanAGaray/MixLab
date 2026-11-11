# Generated manually for prep watch video play button

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0075_prep_hero_video'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='prep_watch_video',
            field=models.FileField(
                blank=True,
                help_text='Video que se abre al pulsar el botón de play (con audio).',
                null=True,
                upload_to='portfolio/prep/',
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=['mp4', 'webm', 'mov']
                    )
                ],
                verbose_name='Video “Ver preparación”',
            ),
        ),
    ]
