from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0060_rental_req_company_fields_nullable'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            UPDATE store_rentalcontractrequirements
               SET damage_terms_acknowledged = COALESCE(damage_terms_acknowledged, FALSE),
                   codeudor_required = COALESCE(codeudor_required, FALSE);

            ALTER TABLE store_rentalcontractrequirements
                ALTER COLUMN damage_terms_acknowledged SET DEFAULT FALSE,
                ALTER COLUMN damage_terms_acknowledged SET NOT NULL,
                ALTER COLUMN codeudor_required SET DEFAULT FALSE,
                ALTER COLUMN codeudor_required SET NOT NULL;

            -- Defaults de texto por si algún INSERT omite columnas NOT NULL.
            ALTER TABLE store_rentalcontractrequirements
                ALTER COLUMN representative_name SET DEFAULT '',
                ALTER COLUMN tenant_name SET DEFAULT '',
                ALTER COLUMN notes SET DEFAULT '',
                ALTER COLUMN location_text SET DEFAULT '',
                ALTER COLUMN maps_url SET DEFAULT '',
                ALTER COLUMN codeudor_name SET DEFAULT '',
                ALTER COLUMN codeudor_document SET DEFAULT '',
                ALTER COLUMN access_password_hash SET DEFAULT '',
                ALTER COLUMN access_password SET DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='damage_terms_acknowledged',
            field=models.BooleanField(
                db_default=False,
                default=False,
                verbose_name='Aceptó tabla de daños y pérdidas',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='codeudor_required',
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text='Si está activo, el cliente debe registrar datos del codeudor en el formulario móvil.',
                verbose_name='Requiere codeudor',
            ),
        ),
    ]
