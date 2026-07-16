from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0021_productrentalprice'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='accent_color',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Opcional. Hex (#0F6FFF). Se usa como fondo o acento en vitrinas y fichas del producto.',
                max_length=7,
                verbose_name='Color de diseño',
            ),
        ),
    ]
