from django.db import migrations, models


def seed_mixlab_registry(apps, schema_editor):
    SiteSettings = apps.get_model('store', 'SiteSettings')
    obj, _ = SiteSettings.objects.get_or_create(pk=1)
    obj.company_legal_name = 'MIXLAB SAS'
    obj.company_nit = '902031074-1'
    obj.company_address = 'Barrio Ciudad Bicentenario, Conjunto Residencial Parques de Bolívar 2'
    obj.company_department = 'Bolívar'
    obj.company_matricula = '10006865'
    obj.jurisdiction_city = 'Cartagena'
    obj.address_city = 'Cartagena'
    obj.address_country = 'Colombia'
    obj.contact_email = 'juandam594@gmail.com'
    obj.contact_phone = '3128104046'
    if not (obj.whatsapp_number or '').strip() or obj.whatsapp_number in ('573045379501', '+573045379501'):
        obj.whatsapp_number = '573128104046'
    obj.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0028_rental_contract_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='company_department',
            field=models.CharField(
                blank=True,
                default='Bolívar',
                max_length=100,
                verbose_name='Departamento',
            ),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='company_matricula',
            field=models.CharField(
                blank=True,
                default='10006865',
                help_text='Número de matrícula en Cámara de Comercio.',
                max_length=40,
                verbose_name='Matrícula mercantil',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='company_legal_name',
            field=models.CharField(
                blank=True,
                default='MIXLAB SAS',
                max_length=200,
                verbose_name='Razón social (arrendador)',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='company_nit',
            field=models.CharField(
                blank=True,
                default='902031074-1',
                max_length=40,
                verbose_name='NIT del arrendador',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='company_address',
            field=models.CharField(
                blank=True,
                default='Barrio Ciudad Bicentenario, Conjunto Residencial Parques de Bolívar 2',
                max_length=255,
                verbose_name='Dirección del arrendador',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='contact_email',
            field=models.EmailField(
                default='juandam594@gmail.com',
                max_length=254,
                verbose_name='Correo de contacto',
            ),
        ),
        migrations.AlterField(
            model_name='sitesettings',
            name='contact_phone',
            field=models.CharField(
                default='3128104046',
                max_length=30,
                verbose_name='Teléfono (visualización)',
            ),
        ),
        migrations.RunPython(seed_mixlab_registry, noop_reverse),
    ]
