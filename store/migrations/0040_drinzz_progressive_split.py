from decimal import Decimal

from django.db import migrations, models


def update_drinzz_defaults(apps, schema_editor):
    DrinzzContractConfig = apps.get_model('store', 'DrinzzContractConfig')
    obj = DrinzzContractConfig.objects.filter(pk=1).first()
    if not obj:
        return
    obj.associate_pct = 30
    obj.operator_pct = 70
    obj.associate_pct_month1 = 20
    obj.operator_pct_month1 = 80
    obj.billing_threshold = Decimal('6000000.00')
    obj.maintain_bonus_pct = 10
    obj.estimated_income_min = Decimal('500000.00')
    obj.estimated_income_max = Decimal('3500000.00')
    obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0039_drinzzcontractconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='drinzzcontractconfig',
            name='associate_pct_month1',
            field=models.PositiveIntegerField(default=20, verbose_name='% utilidades asociado (primer mes)'),
        ),
        migrations.AddField(
            model_name='drinzzcontractconfig',
            name='operator_pct_month1',
            field=models.PositiveIntegerField(default=80, verbose_name='% utilidades operador (primer mes)'),
        ),
        migrations.AddField(
            model_name='drinzzcontractconfig',
            name='billing_threshold',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('6000000.00'),
                help_text='Facturación mensual a partir de la cual aplica el reparto 30/70.',
                max_digits=14,
                verbose_name='Umbral de facturación mensual (COP)',
            ),
        ),
        migrations.AddField(
            model_name='drinzzcontractconfig',
            name='maintain_bonus_pct',
            field=models.PositiveIntegerField(
                default=10,
                help_text='Si se mantiene facturación sobre el umbral en meses siguientes, la liquidación del asociado sube este porcentaje.',
                verbose_name='% bonificación por mantener meta',
            ),
        ),
        migrations.AlterField(
            model_name='drinzzcontractconfig',
            name='associate_pct',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Porcentaje del asociado cuando la facturación mensual supera el umbral.',
                verbose_name='% utilidades asociado (meta facturación)',
            ),
        ),
        migrations.AlterField(
            model_name='drinzzcontractconfig',
            name='operator_pct',
            field=models.PositiveIntegerField(
                default=70,
                help_text='Porcentaje del operador cuando la facturación mensual supera el umbral.',
                verbose_name='% utilidades operador (meta facturación)',
            ),
        ),
        migrations.AlterField(
            model_name='drinzzcontractconfig',
            name='estimated_income_max',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('3500000.00'),
                max_digits=12,
                verbose_name='Ingreso estimado máximo asociado (COP)',
            ),
        ),
        migrations.RunPython(update_drinzz_defaults, migrations.RunPython.noop),
    ]
