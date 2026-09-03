from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0056_sitesettings_cuenta_cobro'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='company_is_grand_contributor',
            field=models.BooleanField(
                default=False,
                help_text='Desmarcado: MIXLAB no es Gran Contribuyente (caso habitual). Afecta textos y retención de IVA en cuenta de cobro.',
                verbose_name='¿Es Gran Contribuyente?',
            ),
        ),
    ]
