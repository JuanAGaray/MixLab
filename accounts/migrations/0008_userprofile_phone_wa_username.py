from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_userprofile_document_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(
                blank=True,
                max_length=80,
                verbose_name='Teléfono',
            ),
        ),
    ]
