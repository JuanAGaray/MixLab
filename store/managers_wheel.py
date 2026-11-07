"""Rueda mensual de 8 decisiones — calendario laboral SVG + persistencia."""
from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Iterable

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .managers_models import (
    ManagerDecisionGoal,
    ManagerSettings,
    PointLedger,
    SalesDecisionDef,
    SalesDecisionLog,
    SalesDecisionProgress,
    SalesMonthCell,
    SalesWheelBoard,
)
from .managers_services import ensure_manager_profile, week_key, week_start


DEFAULT_DECISIONS = [
    # code, name, short, order, target, period, every_n, pts, is_score, color
    ('referidos', 'Conseguir 2 referidos diarios', 'Referidos', 1, 2, 'daily', 1, 2, False, '#22c55e'),
    ('llamadas', 'Realizar 3 llamadas comerciales diarias', 'Llamadas', 2, 3, 'daily', 1, 2, False, '#3b82f6'),
    ('videos', 'Publicar 4 videos comerciales diarios', 'Videos', 3, 4, 'daily', 1, 3, False, '#ef4444'),
    ('historias', 'Publicar 5 historias comerciales diarias', 'Historias', 4, 5, 'daily', 1, 1, False, '#a855f7'),
    ('cotizacion', 'Elaborar al menos 1 cotización diaria', 'Cotización', 5, 1, 'daily', 1, 5, False, '#eab308'),
    ('whatsapp', 'Realizar 25 contactos o seguimientos por WhatsApp diarios', 'WhatsApp', 6, 25, 'daily', 1, 1, False, '#14b8a6'),
    ('testimonio', 'Conseguir 1 testimonio de cliente cada 3 días', 'Testimonio', 7, 1, 'every_n_days', 3, 3, False, '#ec4899'),
    ('score', 'Lograr la meta de puntuación comercial del periodo', 'Meta puntos', 8, 172, 'monthly', 1, 0, True, '#f97316'),
]

MONTH_NAMES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]
WEEKDAY_ABBR_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def seed_sales_decisions() -> int:
    created = 0
    for code, name, short, order, target, period, every_n, pts, is_score, color in DEFAULT_DECISIONS:
        _, was = SalesDecisionDef.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'short_label': short,
                'order': order,
                'default_target': target,
                'period_kind': period,
                'every_n_days': every_n,
                'points_per_unit': pts,
                'is_score_goal': is_score,
                'is_active': True,
                'color': color,
            },
        )
        if was:
            created += 1
    settings = ManagerSettings.load()
    if not settings.wheel_cell_count:
        settings.wheel_cell_count = 144
        settings.save()
    return created


def period_bounds(period_type: str, day: date | None = None) -> tuple[str, date, date]:
    day = day or timezone.localdate()
    if period_type == 'daily':
        return day.isoformat(), day, day
    if period_type == 'monthly':
        start = day.replace(day=1)
        last = calendar.monthrange(start.year, start.month)[1]
        end = start.replace(day=last)
        return f'{day.year}-{day.month:02d}', start, end
    start = week_start(day)
    end = start + timedelta(days=6)
    return week_key(day), start, end


def decision_target_for(user: User, decision: SalesDecisionDef) -> int:
    override = ManagerDecisionGoal.objects.filter(manager=user, decision=decision).first()
    if override:
        return override.target
    return decision.default_target


def decisions_for_manager(user: User) -> list[SalesDecisionDef]:
    profile = ensure_manager_profile(user)
    out = []
    for d in SalesDecisionDef.objects.filter(is_active=True).order_by('order'):
        role = (d.role_filter or '').strip().lower()
        if role and role != (profile.role_label or '').strip().lower():
            continue
        out.append(d)
    return out


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # sáb=5, dom=6


def iter_month_days(year: int, month: int) -> list[date]:
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, last + 1)]


def working_days_in_month(year: int, month: int) -> list[date]:
    return [d for d in iter_month_days(year, month) if not is_weekend(d)]


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    m0 = year * 12 + (month - 1) + delta
    return m0 // 12, m0 % 12 + 1


@transaction.atomic
def get_or_create_month_board(user: User, year: int | None = None, month: int | None = None) -> SalesWheelBoard:
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    ref = date(year, month, 1)
    key, start, end = period_bounds('monthly', ref)
    settings = ManagerSettings.load()
    profile = ensure_manager_profile(user)

    board, created = SalesWheelBoard.objects.get_or_create(
        manager=user,
        period_type='monthly',
        period_key=key,
        defaults={
            'period_start': start,
            'period_end': end,
            'modality': 'activities',
            'cell_count': 0,
            'ring_count': 8,
            'target_points': settings.wheel_target_points or profile.weekly_goal_points or 172,
            'max_points': settings.wheel_max_points or 203,
            'points_per_cell': 1,
        },
    )
    if not created:
        # Asegurar fechas correctas si el mes tiene longitud distinta
        if board.period_start != start or board.period_end != end:
            board.period_start = start
            board.period_end = end
            board.save(update_fields=['period_start', 'period_end', 'updated_at'])

    decisions = decisions_for_manager(user)
    for d in decisions:
        target = decision_target_for(user, d)
        if d.is_score_goal:
            target = board.target_points
        SalesDecisionProgress.objects.get_or_create(
            board=board,
            decision=d,
            defaults={'target': target, 'current': 0},
        )

    ensure_month_cells(board, decisions)
    return board


def daily_target_for(user: User, decision: SalesDecisionDef, board: SalesWheelBoard) -> int:
    """Meta aplicable a un día laboral (no confundir con meta mensual agregada)."""
    if decision.is_score_goal:
        # Meta diaria de puntos ≈ meta del mes / días laborales
        wd = len(working_days_in_month(board.period_start.year, board.period_start.month)) or 1
        return max(1, math.ceil(board.target_points / wd))
    return decision_target_for(user, decision)


def ensure_month_cells(board: SalesWheelBoard, decisions: Iterable[SalesDecisionDef] | None = None):
    decisions = list(decisions or decisions_for_manager(board.manager))
    days = iter_month_days(board.period_start.year, board.period_start.month)
    existing = {
        (c.decision_id, c.day): c
        for c in board.month_cells.select_related('decision')
    }
    to_create = []
    for d in decisions:
        day_target = daily_target_for(board.manager, d, board)
        for day_date in days:
            key = (d.id, day_date.day)
            if key in existing:
                cell = existing[key]
                # Mantener weekend/na
                if is_weekend(day_date):
                    if cell.state != 'weekend':
                        cell.state = 'weekend'
                        cell.units = 0
                        cell.target = day_target
                        cell.activity_date = day_date
                        cell.save(update_fields=['state', 'units', 'target', 'activity_date', 'updated_at'])
                continue
            state = 'weekend' if is_weekend(day_date) else 'pending'
            to_create.append(SalesMonthCell(
                board=board,
                decision=d,
                day=day_date.day,
                activity_date=day_date,
                units=0,
                target=day_target,
                state=state,
            ))
    if to_create:
        SalesMonthCell.objects.bulk_create(to_create, ignore_conflicts=True)


def _units_on_day(board: SalesWheelBoard, decision_id: int, day_date: date) -> int:
    return int(
        SalesDecisionLog.objects.filter(
            board=board,
            decision_id=decision_id,
            undone=False,
            activity_date=day_date,
        ).aggregate(s=Sum('units'))['s'] or 0
    )


def sync_month_board(board: SalesWheelBoard) -> SalesWheelBoard:
    """Recalcula casillas, progreso y puntos solo con días laborales."""
    decisions = decisions_for_manager(board.manager)
    ensure_month_cells(board, decisions)

    logs = list(
        SalesDecisionLog.objects.filter(board=board, undone=False).values(
            'decision_id', 'activity_date', 'units', 'points_awarded',
        )
    )
    by_key: dict[tuple[int, date], int] = {}
    pts_by_day: dict[date, int] = {}
    pts_total = 0
    for row in logs:
        d_date = row['activity_date']
        if not d_date:
            continue
        key = (row['decision_id'], d_date)
        by_key[key] = by_key.get(key, 0) + int(row['units'] or 0)
        pts = int(row['points_awarded'] or 0)
        pts_total += pts
        pts_by_day[d_date] = pts_by_day.get(d_date, 0) + pts

    ledger_pts = int(
        PointLedger.objects.filter(
            manager=board.manager,
            created_at__date__gte=board.period_start,
            created_at__date__lte=board.period_end,
        ).aggregate(s=Sum('points'))['s'] or 0
    )
    pts_total = max(pts_total, ledger_pts)

    wd_list = working_days_in_month(board.period_start.year, board.period_start.month)
    wd_index = {d: i for i, d in enumerate(wd_list)}

    cells = list(board.month_cells.select_related('decision'))
    done_cells = 0
    applicable = 0
    dirty: list[SalesMonthCell] = []

    for cell in cells:
        old = (cell.state, cell.units, cell.target)
        if is_weekend(cell.activity_date):
            cell.state = 'weekend'
            cell.units = 0
        elif cell.decision.period_kind == 'every_n_days' and not cell.decision.is_score_goal:
            n = max(1, cell.decision.every_n_days or 3)
            idx = wd_index.get(cell.activity_date)
            if idx is None:
                cell.state = 'na'
                cell.units = 0
            elif idx % n != 0:
                cell.state = 'na'
                cell.units = 0
            else:
                units = by_key.get((cell.decision_id, cell.activity_date), 0)
                target = cell.target or daily_target_for(board.manager, cell.decision, board)
                cell.units = units
                cell.target = target
                if units <= 0:
                    cell.state = 'pending'
                elif units >= target:
                    cell.state = 'done'
                else:
                    cell.state = 'progress'
                applicable += 1
                if cell.state == 'done':
                    done_cells += 1
        else:
            if cell.decision.is_score_goal:
                units = pts_by_day.get(cell.activity_date, 0)
                target = daily_target_for(board.manager, cell.decision, board)
            else:
                units = by_key.get((cell.decision_id, cell.activity_date), 0)
                target = cell.target or daily_target_for(board.manager, cell.decision, board)
            cell.units = units
            cell.target = target
            if units <= 0:
                cell.state = 'pending'
            elif units >= target:
                cell.state = 'done'
            else:
                cell.state = 'progress'
            applicable += 1
            if cell.state == 'done':
                done_cells += 1

        if (cell.state, cell.units, cell.target) != old:
            dirty.append(cell)

    if dirty:
        SalesMonthCell.objects.bulk_update(dirty, ['units', 'target', 'state', 'updated_at'], batch_size=200)

    # Progreso mensual por decisión
    prog_rows = list(board.decision_progress.select_related('decision'))
    prog_dirty = []
    for prog in prog_rows:
        d = prog.decision
        d_cells = [c for c in cells if c.decision_id == d.id and c.state not in ('weekend', 'na')]
        if d.is_score_goal:
            prog.current = min(board.target_points, pts_total)
            prog.target = board.target_points
        else:
            prog.current = sum(1 for c in d_cells if c.state == 'done')
            prog.target = max(1, len(d_cells))
        prog_dirty.append(prog)
    if prog_dirty:
        SalesDecisionProgress.objects.bulk_update(prog_dirty, ['current', 'target'], batch_size=50)

    board.points_earned = pts_total
    board.cells_filled = done_cells
    board.cell_count = applicable
    board.save(update_fields=['points_earned', 'cells_filled', 'cell_count', 'updated_at'])
    return board


def month_svg_geometry(board: SalesWheelBoard) -> dict:
    """Geometría SVG: anillo = decisión (ext→int), sector = día del mes."""
    decisions = list(
        board.decision_progress.select_related('decision').order_by('decision__order')
    )
    if not decisions:
        decisions_raw = decisions_for_manager(board.manager)
    else:
        decisions_raw = [p.decision for p in decisions]

    year, month = board.period_start.year, board.period_start.month
    days = iter_month_days(year, month)
    n_days = len(days)
    n_rings = max(1, len(decisions_raw))

    # viewBox 400×400 — centro estable; etiquetas simples (sin rotación)
    cx = cy = 200.0
    outer_r = 155.0
    inner_r = 52.0
    label_r = 168.0
    ring_w = (outer_r - inner_r) / n_rings
    gap_r = 1.15
    gap_a = 0.005

    cell_map = {
        (c.decision_id, c.day): c
        for c in board.month_cells.all()
    }

    def pt(r: float, ang: float) -> tuple[float, float]:
        return (cx + r * math.cos(ang), cy + r * math.sin(ang))

    # Día 1 arriba (-90°), sentido horario
    start_deg = -90.0

    cells_out = []
    day_labels = []

    for di, day_date in enumerate(days):
        t0 = di / n_days
        t1 = (di + 1) / n_days
        aa0 = math.radians(start_deg + t0 * 360.0 + gap_a * 360.0)
        aa1 = math.radians(start_deg + t1 * 360.0 - gap_a * 360.0)
        mid = (aa0 + aa1) / 2

        lx, ly = pt(label_r, mid)
        day_labels.append({
            'day': day_date.day,
            'weekday': WEEKDAY_ABBR_ES[day_date.weekday()],
            'is_weekend': is_weekend(day_date),
            'x': round(lx, 2),
            'y': round(ly, 2),
        })

        for ri, decision in enumerate(decisions_raw):
            r0 = outer_r - ri * ring_w - gap_r * 0.2
            r1 = r0 - ring_w + gap_r
            p1 = pt(r0, aa0)
            p2 = pt(r0, aa1)
            p3 = pt(r1, aa1)
            p4 = pt(r1, aa0)
            large = 1 if (aa1 - aa0) % (2 * math.pi) > math.pi else 0
            path = (
                f'M {p1[0]:.2f} {p1[1]:.2f} '
                f'A {r0:.2f} {r0:.2f} 0 {large} 1 {p2[0]:.2f} {p2[1]:.2f} '
                f'L {p3[0]:.2f} {p3[1]:.2f} '
                f'A {r1:.2f} {r1:.2f} 0 {large} 0 {p4[0]:.2f} {p4[1]:.2f} Z'
            )
            cell = cell_map.get((decision.id, day_date.day))
            state = cell.state if cell else ('weekend' if is_weekend(day_date) else 'pending')
            units = cell.units if cell else 0
            target = cell.target if cell else daily_target_for(board.manager, decision, board)
            cells_out.append({
                'decision_id': decision.id,
                'decision_order': decision.order,
                'day': day_date.day,
                'date': day_date.isoformat(),
                'state': state,
                'units': units,
                'target': target,
                'is_weekend': is_weekend(day_date),
                'path': path,
                'ring': ri,
                'sector': di,
                'color': decision.color,
                'label': decision.short_label or decision.name,
                'clickable': state not in ('weekend', 'na') and day_date <= timezone.localdate(),
            })

    # Badges en el borde izquierdo de cada anillo
    ring_icons = []
    for ri, decision in enumerate(decisions_raw):
        r_mid = outer_r - ri * ring_w - ring_w / 2
        ix, iy = pt(r_mid, math.radians(180))
        ring_icons.append({
            'order': decision.order,
            'color': decision.color,
            'short': decision.short_label or decision.name,
            'x': round(ix, 2),
            'y': round(iy, 2),
            'id': decision.id,
        })

    return {
        'cells': cells_out,
        'day_labels': day_labels,
        'ring_icons': ring_icons,
        'cx': cx,
        'cy': cy,
        'hub_r': inner_r - 2,
        'view': 400,
    }


def board_payload(board: SalesWheelBoard, *, sync: bool = True) -> dict:
    if sync:
        board = sync_month_board(board)
    else:
        board.refresh_from_db()
    profile = ensure_manager_profile(board.manager)
    year, month = board.period_start.year, board.period_start.month
    wd = working_days_in_month(year, month)
    geom = month_svg_geometry(board)

    progress = list(
        board.decision_progress.select_related('decision').order_by('decision__order')
    )
    decisions = []
    sum_done = sum_prog = sum_pend = 0
    for p in progress:
        d = p.decision
        status = 'done' if p.is_done else ('progress' if p.current > 0 else 'pending')
        if status == 'done':
            sum_done += 1
        elif status == 'progress':
            sum_prog += 1
        else:
            sum_pend += 1
        decisions.append({
            'id': d.id,
            'code': d.code,
            'name': d.name,
            'short': d.short_label or d.name,
            'order': d.order,
            'current': p.current,
            'target': p.target,
            'pct': p.pct,
            'is_done': p.is_done,
            'status': status,
            'is_score_goal': d.is_score_goal,
            'color': d.color,
            'points_per_unit': d.points_per_unit,
            'period_kind': d.period_kind,
            'every_n_days': d.every_n_days,
            'daily_target': daily_target_for(board.manager, d, board),
        })

    # % mensual solo días laborales aplicables
    applicable = board.cell_count or 1
    compliance = min(100.0, round(100.0 * board.cells_filled / applicable, 1)) if applicable else 0.0

    cells_by_state = {'done': 0, 'progress': 0, 'pending': 0, 'weekend': 0, 'na': 0}
    for c in geom['cells']:
        cells_by_state[c['state']] = cells_by_state.get(c['state'], 0) + 1

    recent = list(
        SalesDecisionLog.objects
        .filter(board=board, undone=False)
        .select_related('decision')
        .order_by('-created_at')[:10]
    )
    recent_logs = [
        {
            'id': log.id,
            'label': log.decision.short_label or log.decision.name,
            'units': log.units,
            'points': log.points_awarded,
            'date': (log.activity_date or log.effective_date()).isoformat(),
            'at': timezone.localtime(log.created_at).strftime('%H:%M'),
        }
        for log in recent
    ]

    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)

    return {
        'board_id': board.id,
        'period_type': 'monthly',
        'period_key': board.period_key,
        'period_start': board.period_start.isoformat(),
        'period_end': board.period_end.isoformat(),
        'year': year,
        'month': month,
        'month_label': f'{MONTH_NAMES_ES[month]} {year}',
        'prev': {'year': prev_y, 'month': prev_m},
        'next': {'year': next_y, 'month': next_m},
        'working_days': len(wd),
        'total_days': calendar.monthrange(year, month)[1],
        'modality': board.modality,
        'modality_label': board.get_modality_display(),
        'points_earned': board.points_earned,
        'target_points': board.target_points,
        'max_points': board.max_points,
        'compliance_pct': compliance,
        'cells_filled': board.cells_filled,
        'cell_count': board.cell_count,
        'cells_pct': compliance,
        'cells_pending': cells_by_state.get('pending', 0),
        'remaining_points': max(0, board.target_points - board.points_earned),
        'points_per_cell': board.points_per_cell,
        'decisions': decisions,
        'cells': geom['cells'],
        'day_labels': geom['day_labels'],
        'ring_icons': geom['ring_icons'],
        'hub_r': geom['hub_r'],
        'cx': geom['cx'],
        'cy': geom['cy'],
        'view': geom.get('view', 400),
        'hub_month_y': geom['cy'] - 8,
        'hub_name_y': geom['cy'] + 7,
        'hub_role_y': geom['cy'] + 18,
        'manager_name': profile.get_display_name(),
        'manager_role': profile.role_label or 'Manager',
        'summary': {
            'done': sum_done,
            'progress': sum_prog,
            'pending': sum_pend,
            'overdue': 0,
            'cells_done': cells_by_state.get('done', 0),
            'cells_progress': cells_by_state.get('progress', 0),
            'cells_pending': cells_by_state.get('pending', 0),
        },
        'recent_logs': recent_logs,
        'weekday_bar': [
            {'label': 'Lun', 'work': True},
            {'label': 'Mar', 'work': True},
            {'label': 'Mié', 'work': True},
            {'label': 'Jue', 'work': True},
            {'label': 'Vie', 'work': True},
            {'label': 'Sáb', 'work': False},
            {'label': 'Dom', 'work': False},
        ],
    }


@transaction.atomic
def record_decision_units(
    *,
    user: User,
    decision_id: int,
    units: int = 1,
    notes: str = '',
    period_type: str | None = None,
    idempotency_key: str | None = None,
    activity_date: date | None = None,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    if units < 1:
        raise ValueError('Debes registrar al menos 1 unidad.')
    if units > 50:
        raise ValueError('Máximo 50 unidades por registro.')

    decision = SalesDecisionDef.objects.get(id=decision_id, is_active=True)
    if decision.is_score_goal:
        raise ValueError('La meta de puntuación se calcula con tus puntos del día; no se registra manualmente.')

    today = timezone.localdate()
    activity_date = activity_date or today
    if year and month:
        board = get_or_create_month_board(user, year, month)
    else:
        board = get_or_create_month_board(user, activity_date.year, activity_date.month)

    if activity_date < board.period_start or activity_date > board.period_end:
        raise ValueError('La fecha no pertenece al mes de la rueda.')
    if is_weekend(activity_date):
        raise ValueError('Los sábados y domingos no aplican. Elige un día laboral.')
    if activity_date > today:
        raise ValueError('No puedes registrar días futuros.')

    # Testimonio: solo días aplicables
    if decision.period_kind == 'every_n_days':
        n = max(1, decision.every_n_days or 3)
        wd_list = working_days_in_month(board.period_start.year, board.period_start.month)
        try:
            idx = wd_list.index(activity_date)
        except ValueError:
            raise ValueError('Día no laboral.')
        if idx % n != 0:
            raise ValueError(f'Esta actividad aplica cada {n} días laborales.')

    day_target = daily_target_for(user, decision, board)
    current_units = _units_on_day(board, decision.id, activity_date)
    if current_units >= day_target and units > 0:
        # Permitir registrar de más, pero el estado ya estará "done"
        pass

    key = idempotency_key or (
        f'log-{user.id}-{decision.id}-{activity_date.isoformat()}-'
        f'{timezone.now().strftime("%Y%m%d%H%M%S%f")}'
    )
    if SalesDecisionLog.objects.filter(idempotency_key=key).exists():
        return board_payload(board)

    pts = int(decision.points_per_unit or 0) * units
    SalesDecisionLog.objects.create(
        board=board,
        decision=decision,
        units=units,
        points_awarded=pts,
        notes=(notes or '')[:255],
        activity_date=activity_date,
        created_by=user,
        idempotency_key=key,
    )
    if pts > 0:
        PointLedger.objects.get_or_create(
            idempotency_key=f'wheel-earn-{key}'[:80],
            defaults={
                'manager': user,
                'activity': None,
                'entry_type': 'earn',
                'points': pts,
                'reason': f'{decision.short_label or decision.name}: +{units} ({activity_date.isoformat()})',
                'created_by': user,
            },
        )

    return board_payload(board)


@transaction.atomic
def undo_last_log(
    *,
    user: User,
    decision_id: int,
    period_type: str | None = None,
    as_admin: bool = False,
    activity_date: date | None = None,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    today = timezone.localdate()
    activity_date = activity_date or today
    if year and month:
        board = get_or_create_month_board(user, year, month)
    else:
        board = get_or_create_month_board(user, activity_date.year, activity_date.month)

    qs = SalesDecisionLog.objects.filter(
        board=board, decision_id=decision_id, undone=False, activity_date=activity_date,
    )
    log = qs.order_by('-created_at').first()
    if not log:
        # Fallback: último del mes para esa decisión
        log = (
            SalesDecisionLog.objects
            .filter(board=board, decision_id=decision_id, undone=False)
            .order_by('-created_at')
            .first()
        )
    if not log:
        raise ValueError('No hay registros para deshacer.')
    if not as_admin and log.created_by_id != user.id:
        raise PermissionError('Solo puedes deshacer tus propios registros.')
    if not as_admin and log.effective_date() != today and log.created_at.date() != today:
        raise PermissionError('Solo se puede deshacer el mismo día.')

    log.undone = True
    log.undone_at = timezone.now()
    log.undone_by = user
    log.save(update_fields=['undone', 'undone_at', 'undone_by'])

    if log.points_awarded:
        PointLedger.objects.get_or_create(
            idempotency_key=f'wheel-revoke-{log.id}',
            defaults={
                'manager': board.manager,
                'entry_type': 'revoke',
                'points': -abs(log.points_awarded),
                'reason': f'Deshacer: {log.decision.short_label}',
                'created_by': user,
            },
        )

    return board_payload(board)


# Compat: aliases usados por vistas antiguas
def get_or_create_board(user, period_type=None, day=None):
    day = day or timezone.localdate()
    if period_type == 'monthly' or period_type is None:
        return get_or_create_month_board(user, day.year, day.month)
    # Otros periodos redirigen al mes contenedor
    return get_or_create_month_board(user, day.year, day.month)


def sync_board_counters(board):
    return sync_month_board(board)


def wheel_svg_geometry(board, progress_extra=0):
    return month_svg_geometry(board)['cells']
