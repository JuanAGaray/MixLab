from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


EVENT_CONVERSATION_MERMAID = """flowchart TD
    A(["Cliente escribe"]) --> B["M01: Bienvenida y solicitud de datos"]
    B --> C{"¿Fecha, tipo y lugar completos?"}
    C -- No --> D["Solicitar información faltante"]
    D --> B
    C -- Sí --> E["Consultar disponibilidad"]
    E --> F{"¿Hay disponibilidad?"}

    F -- No --> G["M04: Informar y ofrecer alternativas"]
    G --> H{"¿Acepta alternativa?"}
    H -- No --> I["Registrar como perdido"]
    H -- Sí --> E

    F -- Sí --> J["M03: Confirmar disponibilidad"]
    J --> K["M05: Enviar portafolio y precios"]
    K --> L{"¿Responde?"}

    L -- No --> M["M06: Seguimiento 1"]
    M --> N{"¿Responde?"}
    N -- No --> O["M07: Seguimiento 2"]
    O --> P{"¿Responde?"}
    P -- No --> Q["M08: Seguimiento 3"]
    Q --> R{"¿Responde?"}

    R -- No --> S["Evaluar descuento 10%"]
    S --> T{"¿Acepta?"}
    T -- No --> U{"¿Falta un día y hay disponibilidad?"}
    U -- Sí --> V["Evaluar descuento 20%"]
    V --> W{"¿Acepta?"}
    W -- No --> X["Registrar como inactivo o perdido"]
    U -- No --> X
    W -- Sí --> Y["Continuar negociación"]
    T -- Sí --> Y

    L -- Sí --> Z{"¿Está interesado?"}
    N -- Sí --> Z
    P -- Sí --> Z
    R -- Sí --> Z

    Z -- No --> AA["Registrar objeción"]
    AA --> AB{"¿Se puede recuperar?"}
    AB -- Sí --> Y
    AB -- No --> X

    Z -- Sí --> Y
    Y --> AC["M11-M14: Resolver dudas y ajustar servicio"]
    AC --> AD["M15: Enviar propuesta económica"]
    AD --> AE{"¿Acepta?"}
    AE -- No --> AA
    AE -- Sí --> AF["M16: Solicitar abono"]
    AF --> AG{"¿Abono verificado?"}
    AG -- No --> AH["M17: Recordatorio de pago"]
    AH --> AG

    AG -- Sí --> AI["M18: Confirmar reserva"]
    AI --> AJ["M19: Solicitar datos de contratación"]
    AJ --> AK["M20: Seleccionar sabores si falta"]
    AK --> AL["M21: Enviar cotización definitiva"]
    AL --> AM["M22: Confirmar detalles del evento"]
    AM --> AN["M23: Gestionar cambios si existen"]
    AN --> AO["Ejecutar servicio"]
    AO --> AP["M24: Mensaje de agradecimiento"]
    AP --> AQ["M25: Solicitar opinión y recomendación"]
    AQ --> AR(["FIN: Cliente fidelizado"])
"""


def seed_event_conversation(apps, schema_editor):
    from django.utils import timezone

    FlowDiagram = apps.get_model('store', 'FlowDiagram')
    if FlowDiagram.objects.filter(slug='conversacion-eventos').exists():
        return
    FlowDiagram.objects.create(
        title='Conversación de eventos',
        slug='conversacion-eventos',
        description=(
            'Flujo completo de atención comercial por WhatsApp/chat para eventos: '
            'datos, disponibilidad, seguimientos, descuentos, propuesta, abono y fidelización.'
        ),
        category='conversacion',
        mermaid_source=EVENT_CONVERSATION_MERMAID.strip(),
        status='published',
        sort_order=1,
        published_at=timezone.now(),
    )


def unseed_event_conversation(apps, schema_editor):
    FlowDiagram = apps.get_model('store', 'FlowDiagram')
    FlowDiagram.objects.filter(slug='conversacion-eventos').delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0068_portfolio_cover'),
    ]

    operations = [
        migrations.CreateModel(
            name='FlowDiagram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('slug', models.SlugField(max_length=220, unique=True, verbose_name='Slug')),
                ('description', models.TextField(blank=True, default='', verbose_name='Descripción')),
                (
                    'category',
                    models.CharField(
                        blank=True,
                        default='general',
                        help_text='Ej: conversacion, operaciones, ventas.',
                        max_length=80,
                        verbose_name='Categoría',
                    ),
                ),
                (
                    'mermaid_source',
                    models.TextField(
                        help_text='Diagrama en sintaxis Mermaid (flowchart, sequence, etc.).',
                        verbose_name='Código Mermaid',
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[('draft', 'Borrador'), ('published', 'Publicado')],
                        db_index=True,
                        default='draft',
                        max_length=20,
                        verbose_name='Estado',
                    ),
                ),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='Publicado en')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='flow_diagrams_created',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Creado por',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Diagrama de flujo',
                'verbose_name_plural': 'Diagramas de flujo',
                'ordering': ['sort_order', 'title'],
            },
        ),
        migrations.RunPython(seed_event_conversation, unseed_event_conversation),
    ]
