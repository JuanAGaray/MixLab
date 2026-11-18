from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0076_prep_watch_video'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuotationItemImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='quotations/line_images/', verbose_name='Imagen')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_images', to='store.quotationitem', verbose_name='Ítem')),
            ],
            options={
                'verbose_name': 'Imagen de ítem de cotización',
                'verbose_name_plural': 'Imágenes de ítems de cotización',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
