from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0059_dian_habilitacion_batch'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            UPDATE store_rentalcontractrequirements
               SET company_legal_rep_document = COALESCE(company_legal_rep_document, ''),
                   company_legal_rep_name = COALESCE(company_legal_rep_name, ''),
                   company_nit = COALESCE(company_nit, ''),
                   conditions_signer_name = COALESCE(conditions_signer_name, ''),
                   conditions_signer_document = COALESCE(conditions_signer_document, '');
            ALTER TABLE store_rentalcontractrequirements
                ALTER COLUMN company_legal_rep_document SET DEFAULT '',
                ALTER COLUMN company_legal_rep_name SET DEFAULT '',
                ALTER COLUMN company_nit SET DEFAULT '',
                ALTER COLUMN conditions_signer_name SET DEFAULT '',
                ALTER COLUMN conditions_signer_document SET DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='company_legal_rep_document',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=30,
                null=True,
                verbose_name='Cédula del representante legal',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='company_legal_rep_name',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=200,
                null=True,
                verbose_name='Representante legal (empresa)',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='company_nit',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=30,
                null=True,
                verbose_name='NIT de la empresa',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='conditions_signer_document',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=30,
                null=True,
                verbose_name='Documento quien acepta condiciones',
            ),
        ),
        migrations.AlterField(
            model_name='rentalcontractrequirements',
            name='conditions_signer_name',
            field=models.CharField(
                blank=True,
                db_default='',
                default='',
                max_length=200,
                null=True,
                verbose_name='Nombre quien acepta condiciones',
            ),
        ),
    ]
