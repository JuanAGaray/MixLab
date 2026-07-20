from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0038_quotation_partial_payment_amount'),
    ]

    operations = [
        migrations.CreateModel(
            name='DrinzzContractConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operator_brand', models.CharField(default='Drinzz', max_length=120, verbose_name='Marca del operador')),
                ('operator_legal_name', models.CharField(blank=True, default='MIXLAB SAS', help_text='Persona jurídica que opera/representa el modelo Drinzz.', max_length=200, verbose_name='Razón social del operador')),
                ('operator_nit', models.CharField(blank=True, default='902031074-1', max_length=40, verbose_name='NIT del operador')),
                ('operator_address', models.CharField(blank=True, default='', max_length=255, verbose_name='Dirección del operador')),
                ('operator_city', models.CharField(blank=True, default='Cartagena', max_length=100, verbose_name='Ciudad del operador')),
                ('operator_rep_name', models.CharField(blank=True, default='', max_length=200, verbose_name='Representante legal del operador')),
                ('associate_pct', models.PositiveIntegerField(default=30, help_text='Porcentaje de utilidades netas para el asociado (dueño del local).', verbose_name='% utilidades asociado')),
                ('operator_pct', models.PositiveIntegerField(default=70, help_text='Porcentaje de utilidades netas para el operador (Drinzz).', verbose_name='% utilidades operador')),
                ('expenses_assumed', models.TextField(default='Luz (consumo eléctrico del punto), insumos (bases, vasos, tapas y consumibles) y alquiler conforme al esquema del punto.', verbose_name='Gastos asumidos por el operador')),
                ('provides_operators', models.BooleanField(default=True, verbose_name='El operador puede colocar personal operador')),
                ('estimated_income_min', models.DecimalField(decimal_places=2, default=Decimal('500000.00'), max_digits=12, verbose_name='Ingreso estimado mínimo asociado (COP)')),
                ('estimated_income_max', models.DecimalField(decimal_places=2, default=Decimal('1500000.00'), max_digits=12, verbose_name='Ingreso estimado máximo asociado (COP)')),
                ('contract_duration_months', models.PositiveIntegerField(default=12, verbose_name='Duración inicial (meses)')),
                ('renewal_auto', models.BooleanField(default=True, verbose_name='Renovación automática')),
                ('termination_notice_days', models.PositiveIntegerField(default=30, verbose_name='Días de preaviso para terminación')),
                ('settlement_days', models.PositiveIntegerField(default=10, help_text='Plazo para liquidar y pagar utilidades del periodo.', verbose_name='Días hábiles para liquidación de utilidades')),
                ('jurisdiction_city', models.CharField(default='Cartagena', max_length=100, verbose_name='Ciudad de jurisdicción')),
                ('object_clause', models.TextField(default='El presente contrato tiene por objeto establecer una colaboración operativa para la instalación, puesta en marcha y explotación de un punto de venta de granizados (bebidas congeladas) dentro de un local comercial del ASOCIADO, bajo la marca y modelo operativo Drinzz. El OPERADOR aporta la infraestructura, insumos y operación; el ASOCIADO aporta el espacio físico y el flujo de clientes del establecimiento.', verbose_name='Cláusula de objeto')),
                ('associate_obligations', models.TextField(default='1) Facilitar un espacio adecuado, seguro y visible dentro del local para el punto.\n2) Permitir el acceso del OPERADOR y su personal para instalación, reposición, mantenimiento y operación.\n3) No interferir en la operación diaria ni en la calidad del producto.\n4) Informar de inmediato cualquier daño, hurto, falla o incidente.\n5) Abstenerse de comercializar productos competidores de granizados en el mismo espacio durante la vigencia, salvo autorización escrita del OPERADOR.', verbose_name='Obligaciones del asociado')),
                ('operator_obligations', models.TextField(default='1) Instalar y mantener la infraestructura del punto de granizados.\n2) Asumir los gastos de luz, insumos y alquiler conforme al esquema pactado.\n3) Proveer operadores cuando se acuerde para la atención del punto.\n4) Reponer insumos y garantizar continuidad operativa razonable.\n5) Llevar registro de ventas y liquidar utilidades en los plazos acordados.', verbose_name='Obligaciones del operador')),
                ('additional_clauses', models.TextField(blank=True, default='', help_text='Texto libre que se insertará al final del contrato, antes de firmas. Una cláusula por párrafo.', verbose_name='Cláusulas adicionales (editables)')),
                ('disclaimer_income', models.TextField(default='Las cifras de ingreso estimado del ASOCIADO son referenciales, basadas en la experiencia de puntos en operación, y no constituyen garantía ni promesa de resultados. El rendimiento real depende de ubicación, flujo de clientes, horarios, temporada y demás factores del mercado.', verbose_name='Aviso sobre ingresos estimados')),
                ('version_label', models.CharField(default='v1.0', max_length=40, verbose_name='Versión del contrato')),
                ('is_published', models.BooleanField(default=True, verbose_name='Publicar descarga en la página de alianza')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Contrato Drinzz',
                'verbose_name_plural': 'Contrato Drinzz',
            },
        ),
    ]
