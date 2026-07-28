from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0046_combo_item_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rentalcombo',
            name='slug',
            field=models.SlugField(max_length=200, unique=True, verbose_name='Slug'),
        ),
    ]
