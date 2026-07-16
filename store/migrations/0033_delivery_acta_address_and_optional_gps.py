import re

from django.db import migrations, models


MAPS_RE = re.compile(
    r'^https?://(www\.)?(google\.[^/]+/maps|maps\.google\.[^/]+|maps\.app\.goo\.gl)',
    re.IGNORECASE,
)


def migrate_maps_from_location(apps, schema_editor):
    Acta = apps.get_model('store', 'RentalDeliveryActa')
    for acta in Acta.objects.all():
        loc = (acta.reception_location or '').strip()
        if not loc:
            continue
        if MAPS_RE.search(loc) and not (acta.reception_maps_url or '').strip():
            acta.reception_maps_url = loc[:500]
            acta.reception_location = ''
            acta.save(update_fields=['reception_maps_url', 'reception_location'])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0032_alter_reception_location_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rentaldeliveryacta',
            name='reception_location',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Dirección escrita del lugar donde se entrega/recibe el equipo.',
                max_length=500,
                verbose_name='Dirección de recepción',
            ),
        ),
        migrations.AddField(
            model_name='rentaldeliveryacta',
            name='reception_maps_url',
            field=models.URLField(
                blank=True,
                default='',
                help_text='Opcional. Enlace de Google Maps con la ubicación GPS.',
                max_length=500,
                verbose_name='Ubicación GPS (Google Maps)',
            ),
        ),
        migrations.AddField(
            model_name='rentaldeliveryacta',
            name='reception_latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=10,
                null=True,
                verbose_name='Latitud',
            ),
        ),
        migrations.AddField(
            model_name='rentaldeliveryacta',
            name='reception_longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=10,
                null=True,
                verbose_name='Longitud',
            ),
        ),
        migrations.RunPython(migrate_maps_from_location, migrations.RunPython.noop),
    ]
