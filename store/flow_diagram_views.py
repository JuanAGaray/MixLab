"""Panel de diagramas de flujo (Mermaid): edición staff y vista pública."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .models import FlowDiagram

DEFAULT_MERMAID = """flowchart TD
    A([Inicio]) --> B[Paso 1]
    B --> C{¿Continuar?}
    C -- Sí --> D[Paso 2]
    C -- No --> E([Fin])
    D --> E
"""

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


def _parse_form(request) -> dict:
    title = (request.POST.get('title') or '').strip()
    description = (request.POST.get('description') or '').strip()
    category = (request.POST.get('category') or 'general').strip()[:80] or 'general'
    mermaid_source = (request.POST.get('mermaid_source') or '').strip()
    sort_order_raw = (request.POST.get('sort_order') or '0').strip()
    slug_raw = (request.POST.get('slug') or '').strip()
    try:
        sort_order = max(0, int(sort_order_raw))
    except (TypeError, ValueError):
        sort_order = 0
    return {
        'title': title,
        'description': description,
        'category': category,
        'mermaid_source': mermaid_source,
        'sort_order': sort_order,
        'slug': slugify(slug_raw) if slug_raw else '',
    }


def _validate(data: dict) -> list[str]:
    errors = []
    if not data['title']:
        errors.append('El título es obligatorio.')
    if not data['mermaid_source']:
        errors.append('El código Mermaid es obligatorio.')
    return errors


@staff_member_required
def flow_diagram_list(request):
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    category = (request.GET.get('category') or '').strip()

    qs = FlowDiagram.objects.all()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(slug__icontains=q)
            | Q(category__icontains=q)
        )
    if status in {FlowDiagram.STATUS_DRAFT, FlowDiagram.STATUS_PUBLISHED}:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category__iexact=category)

    categories = (
        FlowDiagram.objects.exclude(category='')
        .order_by('category')
        .values_list('category', flat=True)
        .distinct()
    )

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(
        request,
        'store/flow_diagram_list.html',
        {
            'page_obj': page,
            'diagrams': page.object_list,
            'q': q,
            'status': status,
            'category': category,
            'categories': categories,
            'total_count': FlowDiagram.objects.count(),
            'published_count': FlowDiagram.objects.filter(status=FlowDiagram.STATUS_PUBLISHED).count(),
            'draft_count': FlowDiagram.objects.filter(status=FlowDiagram.STATUS_DRAFT).count(),
        },
    )


@staff_member_required
def flow_diagram_create(request):
    form = {
        'title': '',
        'slug': '',
        'description': '',
        'category': 'conversacion',
        'mermaid_source': DEFAULT_MERMAID,
        'sort_order': 0,
    }
    errors: list[str] = []

    if request.method == 'POST':
        form = _parse_form(request)
        errors = _validate(form)
        if not errors:
            diagram = FlowDiagram(
                title=form['title'],
                description=form['description'],
                category=form['category'],
                mermaid_source=form['mermaid_source'],
                sort_order=form['sort_order'],
                created_by=request.user,
            )
            if form['slug']:
                diagram.slug = form['slug']
            diagram.save()
            messages.success(request, 'Diagrama creado.')
            return redirect('store:flow_diagram_edit', pk=diagram.pk)

    return render(
        request,
        'store/flow_diagram_edit.html',
        {
            'diagram': None,
            'form': form,
            'errors': errors,
            'is_create': True,
            'page_title': 'Nuevo diagrama de flujo',
        },
    )


@staff_member_required
def flow_diagram_edit(request, pk):
    diagram = get_object_or_404(FlowDiagram, pk=pk)
    form = {
        'title': diagram.title,
        'slug': diagram.slug,
        'description': diagram.description,
        'category': diagram.category,
        'mermaid_source': diagram.mermaid_source,
        'sort_order': diagram.sort_order,
    }
    errors: list[str] = []

    if request.method == 'POST':
        form = _parse_form(request)
        errors = _validate(form)
        if form['slug'] and form['slug'] != diagram.slug:
            if FlowDiagram.objects.filter(slug=form['slug']).exclude(pk=diagram.pk).exists():
                errors.append('Ese slug ya está en uso.')
        if not errors:
            diagram.title = form['title']
            diagram.description = form['description']
            diagram.category = form['category']
            diagram.mermaid_source = form['mermaid_source']
            diagram.sort_order = form['sort_order']
            if form['slug']:
                diagram.slug = form['slug']
            diagram.save()
            messages.success(request, 'Diagrama actualizado.')
            return redirect('store:flow_diagram_edit', pk=diagram.pk)

    return render(
        request,
        'store/flow_diagram_edit.html',
        {
            'diagram': diagram,
            'form': form,
            'errors': errors,
            'is_create': False,
            'page_title': f'Editar · {diagram.title}',
        },
    )


@staff_member_required
@require_POST
def flow_diagram_publish(request, pk):
    diagram = get_object_or_404(FlowDiagram, pk=pk)
    action = (request.POST.get('action') or 'publish').strip()
    if action == 'unpublish':
        diagram.unpublish()
        messages.info(request, f'“{diagram.title}” pasó a borrador.')
    else:
        diagram.publish()
        messages.success(request, f'“{diagram.title}” publicado.')
    next_url = request.POST.get('next') or reverse('store:flow_diagram_list')
    return redirect(next_url)


@staff_member_required
@require_POST
def flow_diagram_delete(request, pk):
    diagram = get_object_or_404(FlowDiagram, pk=pk)
    title = diagram.title
    diagram.delete()
    messages.warning(request, f'Diagrama “{title}” eliminado.')
    return redirect('store:flow_diagram_list')


@staff_member_required
def flow_diagram_public_list(request):
    """Vista de lectura para managers (staff). Incluye publicados y borradores."""
    diagrams = FlowDiagram.objects.all()
    category = (request.GET.get('category') or '').strip()
    status = (request.GET.get('status') or '').strip()
    if category:
        diagrams = diagrams.filter(category__iexact=category)
    if status in {FlowDiagram.STATUS_DRAFT, FlowDiagram.STATUS_PUBLISHED}:
        diagrams = diagrams.filter(status=status)
    categories = (
        FlowDiagram.objects.exclude(category='')
        .order_by('category')
        .values_list('category', flat=True)
        .distinct()
    )
    return render(
        request,
        'store/flow_diagram_public_list.html',
        {
            'diagrams': diagrams,
            'categories': categories,
            'category': category,
            'status': status,
            'is_manager_view': True,
        },
    )


@staff_member_required
def flow_diagram_public_detail(request, slug):
    """Detalle de diagrama para managers (staff); permite ver borradores."""
    diagram = get_object_or_404(FlowDiagram, slug=slug)
    return render(
        request,
        'store/flow_diagram_public_detail.html',
        {'diagram': diagram, 'is_manager_view': True},
    )
