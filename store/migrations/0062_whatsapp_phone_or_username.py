from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0061_rental_req_boolean_db_defaults'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotation',
            name='client_phone',
            field=models.CharField(
                blank=True,
                help_text='Celular o usuario de WhatsApp (ej. 3001234567 o @usuario).',
                max_length=64,
                verbose_name='Teléfono o usuario WhatsApp',
            ),
        ),
        migrations.AlterField(
            model_name='combobooking',
            name='client_phone',
            field=models.CharField(
                blank=True,
                default='',
                max_length=64,
                verbose_name='Teléfono o usuario WhatsApp',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='whatsapp_number',
            field=models.CharField(
                default='573128104046',
                help_text='Celular con código de país (573045379501) o usuario (@usuario). Se usa en el botón flotante y wa.me.',
                max_length=64,
                verbose_name='WhatsApp (celular o usuario)',
            ),
        ),
    ]
