from django.db import migrations, models


TRANSPARENCY_DEFAULT = (
    'Todas las compras, gastos y ventas del punto se registrarán de manera automatizada '
    'a través de la plataforma Biztra, con el fin de garantizar total transparencia '
    'frente al ASOCIADO. El ASOCIADO podrá conocer, conforme a los accesos y reportes '
    'habilitados, la información de ventas, costos y liquidaciones del punto. '
    'Las partes reconocen que Biztra es la fuente operativa de registro para efectos '
    'de control, seguimiento y liquidación de utilidades.'
)

OPERATOR_OBLIGATIONS_DEFAULT = (
    '1) Instalar y mantener la infraestructura del punto de granizados.\n'
    '2) Asumir los gastos de luz, insumos y alquiler conforme al esquema pactado.\n'
    '3) Proveer operadores cuando se acuerde para la atención del punto.\n'
    '4) Reponer insumos y garantizar continuidad operativa razonable.\n'
    '5) Registrar compras, gastos y ventas del punto de forma automatizada en Biztra, '
    'garantizando transparencia total en la información operativa y financiera.\n'
    '6) Liquidar utilidades en los plazos acordados con base en los registros del sistema.'
)


def update_transparency(apps, schema_editor):
    DrinzzContractConfig = apps.get_model('store', 'DrinzzContractConfig')
    obj = DrinzzContractConfig.objects.filter(pk=1).first()
    if not obj:
        return
    obj.transparency_clause = TRANSPARENCY_DEFAULT
    # Solo actualizar obligaciones si aún tiene el texto corto anterior
    if 'Biztra' not in (obj.operator_obligations or ''):
        obj.operator_obligations = OPERATOR_OBLIGATIONS_DEFAULT
    obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0040_drinzz_progressive_split'),
    ]

    operations = [
        migrations.AddField(
            model_name='drinzzcontractconfig',
            name='transparency_clause',
            field=models.TextField(
                default=TRANSPARENCY_DEFAULT,
                help_text='Se incluye en el contrato PDF y en la página de alianza.',
                verbose_name='Cláusula de transparencia (Biztra)',
            ),
        ),
        migrations.AlterField(
            model_name='drinzzcontractconfig',
            name='operator_obligations',
            field=models.TextField(
                default=OPERATOR_OBLIGATIONS_DEFAULT,
                verbose_name='Obligaciones del operador',
            ),
        ),
        migrations.RunPython(update_transparency, migrations.RunPython.noop),
    ]
