from django.db import migrations, models


POST_PAYMENT = ('pago_recibido', 'enviado', 'recibido', 'modificado_y_enviado')


def mark_already_deducted(apps, schema_editor):
    """
    Cotizaciones que ya pasaron por estados post-pago ya descontaron stock
    con la lógica anterior; marcarlas para no volver a restar.
    """
    Quotation = apps.get_model('store', 'Quotation')
    Quotation.objects.filter(order_status__in=POST_PAYMENT).update(stock_deducted=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0024_product_unit_quantity'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='stock_deducted',
            field=models.BooleanField(
                default=False,
                help_text='Indica si el inventario de esta cotización ya fue restado.',
                verbose_name='Stock descontado',
            ),
        ),
        migrations.RunPython(mark_already_deducted, noop_reverse),
    ]
