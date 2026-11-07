"""Servicios de MixLab Managers: puntos, periodos, instancias y métricas."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .managers_models import (
    ActivityCategory,
    ActivityInstance,
    ActivityTemplate,
    ManagerProfile,
    ManagerSettings,
    ManagerWeekSnapshot,
    PointLedger,
)
from .models import Quotation


def week_start(d: date | None = None) -> date:
    d = d or timezone.localdate()
    return d - timedelta(days=d.weekday())


def week_key(d: date | None = None) -> str:
    d = d or timezone.localdate()
    iso = d.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def period_key_for_template(template: ActivityTemplate, d: date | None = None) -> str:
    d = d or timezone.localdate()
    if template.frequency == 'weekly':
        return week_key(d)
    if template.frequency == 'once':
        return f'once-{template.id}'
    return d.isoformat()


def ensure_manager_profile(user: User) -> ManagerProfile:
    settings_obj = ManagerSettings.load()
    profile, created = ManagerProfile.objects.get_or_create(
        user=user,
        defaults={
            'display_name': (user.get_full_name() or user.username or '').strip(),
            'daily_goal_points': settings_obj.default_daily_goal,
            'weekly_goal_points': settings_obj.default_weekly_goal,
            'is_active': True,
        },
    )
    return profile


def ensure_today_instances(user: User, day: date | None = None) -> list[ActivityInstance]:
    """Crea instancias del día/semana para plantillas activas sin duplicar."""
    day = day or timezone.localdate()
    ensure_manager_profile(user)
    created = []
    templates = (
        ActivityTemplate.objects
        .filter(is_active=True, category__is_active=True)
        .select_related('category')
        .order_by('order', 'id')
    )
    for tpl in templates:
        pkey = period_key_for_template(tpl, day)
        due = day
        if tpl.frequency == 'weekly':
            due = week_start(day) + timedelta(days=6)
        obj, was_created = ActivityInstance.objects.get_or_create(
            template=tpl,
            assignee=user,
            period_key=pkey,
            defaults={
                'title': tpl.name,
                'description': tpl.description,
                'points_possible': tpl.points,
                'due_date': due,
                'status': 'pending',
            },
        )
        if was_created:
            created.append(obj)
    return created


def points_earned_between(user: User, start: date, end: date) -> int:
    qs = PointLedger.objects.filter(
        manager=user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )
    total = qs.aggregate(s=Sum('points'))['s']
    return int(total or 0)


def points_today(user: User, day: date | None = None) -> int:
    day = day or timezone.localdate()
    return points_earned_between(user, day, day)


def points_this_week(user: User, day: date | None = None) -> int:
    day = day or timezone.localdate()
    start = week_start(day)
    end = start + timedelta(days=6)
    return points_earned_between(user, start, end)


def streak_days(user: User, day: date | None = None, lookback: int = 30) -> int:
    """Días consecutivos (hacia atrás) cumpliendo meta diaria."""
    day = day or timezone.localdate()
    profile = ensure_manager_profile(user)
    goal = profile.daily_goal_points or 1
    streak = 0
    cursor = day - timedelta(days=1)  # racha por días cerrados; hoy aparte
    for _ in range(lookback):
        earned = points_today(user, cursor)
        if earned >= goal:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    # Si hoy ya cumple, sumar hoy
    if points_today(user, day) >= goal:
        streak += 1
    return streak


def count_points_today_for_template(user: User, template: ActivityTemplate, day: date | None = None) -> int:
    day = day or timezone.localdate()
    qs = PointLedger.objects.filter(
        manager=user,
        entry_type='earn',
        created_at__date=day,
        activity__template=template,
    )
    return int(qs.aggregate(s=Sum('points'))['s'] or 0)


@transaction.atomic
def submit_activity_completion(
    *,
    instance: ActivityInstance,
    user: User,
    notes: str = '',
    evidence=None,
    quotation_id: int | None = None,
) -> ActivityInstance:
    if instance.assignee_id != user.id and not user.is_superuser:
        raise PermissionError('No puedes completar actividades de otro manager.')
    if instance.status in ('validated', 'expired'):
        raise ValueError('Esta actividad ya no admite cambios de estado.')

    tpl = instance.template
    if tpl.requires_evidence and not evidence and not instance.evidence:
        raise ValueError('Esta actividad requiere evidencia adjunta.')

    # Límite diario de puntos por plantilla
    limit = tpl.daily_limit or 0
    if limit > 0:
        already = count_points_today_for_template(user, tpl)
        if already >= (tpl.points * limit) and instance.status not in ('pending_validation', 'completed'):
            # Si ya está en revisión, permitir continuar sin nuevo earn
            if instance.status not in ('pending_validation',):
                raise ValueError('Alcanzaste el límite diario de puntos para esta actividad.')

    instance.manager_notes = (notes or '').strip()
    if evidence:
        instance.evidence = evidence
    if quotation_id:
        instance.related_quotation_id = quotation_id
    instance.completed_at = timezone.now()
    if not instance.started_at:
        instance.started_at = timezone.now()

    if tpl.requires_validation:
        instance.status = 'pending_validation'
        instance.points_awarded = 0
        instance.save()
        return instance

    # Auto-validar
    return validate_activity(instance=instance, validator=user, approve=True, notes='Auto-validada')


@transaction.atomic
def validate_activity(
    *,
    instance: ActivityInstance,
    validator: User,
    approve: bool,
    notes: str = '',
) -> ActivityInstance:
    if instance.status == 'validated' and approve:
        return instance  # idempotente

    if not approve:
        instance.status = 'rejected'
        instance.admin_notes = (notes or '').strip()
        instance.validated_by = validator
        instance.validated_at = timezone.now()
        instance.points_awarded = 0
        instance.save()
        # Revocar si hubo puntos previos
        existing = PointLedger.objects.filter(
            activity=instance, entry_type='earn',
        ).first()
        if existing:
            revoke_key = f'revoke-{instance.id}-{existing.id}'
            PointLedger.objects.get_or_create(
                idempotency_key=revoke_key,
                defaults={
                    'manager': instance.assignee,
                    'activity': instance,
                    'entry_type': 'revoke',
                    'points': -abs(existing.points),
                    'reason': f'Revocación actividad #{instance.id}: {notes or "rechazada"}',
                    'created_by': validator,
                },
            )
        return instance

    tpl = instance.template
    # Límite diario
    limit = tpl.daily_limit or 0
    award = int(tpl.points or 0)
    if limit > 0:
        already = count_points_today_for_template(instance.assignee, tpl)
        # Excluir esta misma si ya tenía earn (re-validación)
        prior = PointLedger.objects.filter(
            activity=instance, entry_type='earn',
        ).aggregate(s=Sum('points'))['s'] or 0
        effective_already = int(already) - int(prior)
        max_pts = tpl.points * limit
        if effective_already >= max_pts:
            award = 0
        else:
            award = min(award, max_pts - effective_already)

    instance.status = 'validated'
    instance.points_awarded = award
    instance.validated_by = validator
    instance.validated_at = timezone.now()
    instance.admin_notes = (notes or '').strip()
    if not instance.completed_at:
        instance.completed_at = timezone.now()
    instance.save()

    if award > 0:
        idem = f'earn-{instance.id}'
        PointLedger.objects.get_or_create(
            idempotency_key=idem,
            defaults={
                'manager': instance.assignee,
                'activity': instance,
                'entry_type': 'earn',
                'points': award,
                'reason': f'Actividad validada: {instance.title}',
                'created_by': validator,
            },
        )
    return instance


@transaction.atomic
def adjust_points(*, manager: User, points: int, reason: str, created_by: User) -> PointLedger:
    if points == 0:
        raise ValueError('El ajuste debe ser distinto de cero.')
    key = f'adj-{manager.id}-{timezone.now().strftime("%Y%m%d%H%M%S%f")}-{abs(points)}'
    return PointLedger.objects.create(
        manager=manager,
        activity=None,
        entry_type='adjust',
        points=points,
        reason=(reason or 'Ajuste administrativo')[:255],
        created_by=created_by,
        idempotency_key=key,
    )


def commercial_stats(user: User | None, start: date, end: date) -> dict:
    """Indicadores comerciales reales desde Quotation."""
    qs = Quotation.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    if user is not None:
        qs = qs.filter(created_by=user)

    total = qs.count()
    pending = qs.filter(
        order_status__in=('sin_respuesta', 'aceptado', 'esperando_pago', 'pago_parcial'),
    ).count()
    closed = qs.filter(
        Q(order_status__in=('pago_recibido', 'enviado', 'recibido'))
        | Q(quotation_status='cerrada'),
    )
    closed_count = closed.count()
    revenue = closed.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
    avg = (revenue / closed_count) if closed_count else Decimal('0.00')
    conversion = round(100.0 * closed_count / total, 1) if total else 0.0

    return {
        'quotations_sent': total,
        'quotations_pending': pending,
        'sales_closed': closed_count,
        'revenue': revenue,
        'avg_sale': avg,
        'conversion_pct': conversion,
    }


def ranking_rows(day: date | None = None) -> list[dict]:
    day = day or timezone.localdate()
    start = week_start(day)
    end = start + timedelta(days=6)
    settings_obj = ManagerSettings.load()
    if not settings_obj.ranking_enabled:
        return []

    profiles = (
        ManagerProfile.objects
        .filter(is_active=True, user__is_active=True, user__is_staff=True)
        .select_related('user')
    )
    rows = []
    for p in profiles:
        pts = points_earned_between(p.user, start, end)
        goal = p.weekly_goal_points or 1
        compliance = min(100.0, round(100.0 * max(0, pts) / goal, 1))
        stats = commercial_stats(p.user, start, end)
        rows.append({
            'profile': p,
            'user': p.user,
            'points': pts,
            'goal': goal,
            'compliance': compliance,
            'sales_closed': stats['sales_closed'],
            'revenue': stats['revenue'],
        })
    rows.sort(key=lambda r: (r['compliance'], r['points'], r['sales_closed']), reverse=True)
    for i, r in enumerate(rows, start=1):
        r['position'] = i
    return rows


def refresh_week_snapshot(user: User, day: date | None = None) -> ManagerWeekSnapshot:
    day = day or timezone.localdate()
    start = week_start(day)
    end = start + timedelta(days=6)
    profile = ensure_manager_profile(user)
    pts = points_earned_between(user, start, end)
    acts = ActivityInstance.objects.filter(assignee=user, period_key__startswith=day.isoformat()[:4])
    # Conteos de la semana
    week_acts = ActivityInstance.objects.filter(
        assignee=user,
        due_date__gte=start,
        due_date__lte=end,
    )
    done = week_acts.filter(status='validated').count()
    total = week_acts.count()
    stats = commercial_stats(user, start, end)
    snap, _ = ManagerWeekSnapshot.objects.update_or_create(
        manager=user,
        week_key=week_key(day),
        defaults={
            'week_start': start,
            'target_points': profile.weekly_goal_points,
            'earned_points': pts,
            'activities_done': done,
            'activities_total': total,
            'quotations_count': stats['quotations_sent'],
            'sales_count': stats['sales_closed'],
            'sales_amount': stats['revenue'],
        },
    )
    return snap


def seed_default_catalog() -> dict:
    """Crea categorías y plantillas iniciales si no existen."""
    cats = [
        ('ventas', 'Ventas', '#059669', 'bi-graph-up-arrow', 1),
        ('marketing', 'Marketing', '#0F6FFF', 'bi-camera-reels', 2),
        ('alianzas', 'Alianzas', '#7c3aed', 'bi-handshake', 3),
        ('operaciones', 'Operaciones', '#d97706', 'bi-gear', 4),
        ('gestion', 'Gestión', '#334155', 'bi-clipboard-check', 5),
    ]
    cat_map = {}
    for slug, name, color, icon, order in cats:
        obj, _ = ActivityCategory.objects.update_or_create(
            slug=slug,
            defaults={
                'name': name,
                'color': color,
                'icon': icon,
                'order': order,
                'is_active': True,
            },
        )
        cat_map[slug] = obj

    templates = [
        ('ventas', 'Contactar un cliente potencial', 2, 'daily', 5, False, False, True),
        ('ventas', 'Hacer seguimiento a una cotización', 2, 'daily', 5, False, False, True),
        ('ventas', 'Registrar una venta cerrada', 5, 'daily', 10, True, True, True),
        ('ventas', 'Registrar una oportunidad comercial calificada', 3, 'daily', 5, False, False, False),
        ('marketing', 'Publicar un Reel comercial', 5, 'daily', 1, True, False, True),
        ('marketing', 'Publicar historias comerciales', 2, 'daily', 2, True, False, False),
        ('marketing', 'Obtener un testimonio de cliente', 3, 'weekly', 3, True, True, False),
        ('alianzas', 'Contactar un organizador de eventos', 3, 'daily', 3, False, False, True),
        ('alianzas', 'Conseguir un nuevo aliado comercial', 5, 'weekly', 2, True, True, True),
        ('gestion', 'Revisar indicadores y planificar el siguiente día', 2, 'daily', 1, False, False, True),
        ('operaciones', 'Verificar disponibilidad de máquinas', 2, 'daily', 1, False, False, False),
        ('operaciones', 'Revisar inventario de insumos', 2, 'weekly', 1, False, False, False),
    ]
    created = 0
    for slug, name, pts, freq, limit, evidence, validation, priority in templates:
        _, was = ActivityTemplate.objects.get_or_create(
            category=cat_map[slug],
            name=name,
            defaults={
                'points': pts,
                'frequency': freq,
                'daily_limit': limit,
                'requires_evidence': evidence,
                'requires_validation': validation,
                'is_priority': priority,
                'is_active': True,
            },
        )
        if was:
            created += 1

    ManagerSettings.load()
    # Activar perfiles para staff existente
    for u in User.objects.filter(is_staff=True, is_active=True):
        ensure_manager_profile(u)

    from .managers_wheel import seed_sales_decisions
    decisions_created = seed_sales_decisions()

    return {
        'categories': len(cat_map),
        'templates_created': created,
        'decisions_created': decisions_created,
    }
