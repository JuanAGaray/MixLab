"""Vistas MixLab Managers — dashboard, actividades y administración."""
from datetime import date as date_cls, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .managers_models import (
    ActivityCategory,
    ActivityInstance,
    ActivityTemplate,
    ManagerDecisionGoal,
    ManagerProfile,
    ManagerSettings,
    ManagerWeekSnapshot,
    PointLedger,
    SalesDecisionDef,
    SalesWheelBoard,
)
from .managers_services import (
    commercial_stats,
    ensure_manager_profile,
    ensure_today_instances,
    points_this_week,
    points_today,
    ranking_rows,
    refresh_week_snapshot,
    seed_default_catalog,
    streak_days,
    submit_activity_completion,
    validate_activity,
    week_key,
    week_start,
    adjust_points,
)
from .managers_wheel import (
    board_payload,
    get_or_create_month_board,
    record_decision_units,
    seed_sales_decisions,
    sync_month_board,
    undo_last_log,
)


def _require_manager(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return None
    return ensure_manager_profile(request.user)


@staff_member_required
def managers_dashboard(request):
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')

    today = timezone.localdate()
    seed_sales_decisions()

    try:
        year = int(request.GET.get('year') or today.year)
        month = int(request.GET.get('month') or today.month)
    except (TypeError, ValueError):
        year, month = today.year, today.month
    if month < 1 or month > 12:
        month = today.month

    board = get_or_create_month_board(request.user, year, month)
    payload = board_payload(board, sync=True)

    history = list(
        SalesWheelBoard.objects
        .filter(manager=request.user, period_type='monthly')
        .order_by('-period_start')[:12]
    )

    selected_day = request.GET.get('day')
    try:
        selected_day = int(selected_day) if selected_day else today.day
    except (TypeError, ValueError):
        selected_day = today.day
    if year == today.year and month == today.month:
        selected_day = min(selected_day, today.day)
    else:
        selected_day = min(max(1, selected_day), payload['total_days'])

    return render(request, 'store/managers/dashboard.html', {
        'profile': profile,
        'today': today,
        'period_type': 'monthly',
        'wheel': payload,
        'wheel_data': payload,  # JSON limpio para D3 (evita comas de localización es-co)
        'history': history,
        'selected_day': selected_day,
        'streak': streak_days(request.user, today),
        'pts_today': points_today(request.user, today),
        'pts_week': points_this_week(request.user, today),
    })


@staff_member_required
@require_POST
def managers_decision_add(request):
    """AJAX/POST: sumar unidades a una decisión en un día concreto."""
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')
    try:
        decision_id = int(request.POST.get('decision_id') or 0)
        units = int(request.POST.get('units') or 1)
        notes = (request.POST.get('notes') or '').strip()
        year = int(request.POST.get('year') or timezone.localdate().year)
        month = int(request.POST.get('month') or timezone.localdate().month)
        day = int(request.POST.get('day') or timezone.localdate().day)
        activity_date = date_cls(year, month, day)
        data = record_decision_units(
            user=request.user,
            decision_id=decision_id,
            units=units,
            notes=notes,
            activity_date=activity_date,
            year=year,
            month=month,
            idempotency_key=(request.POST.get('idempotency_key') or '').strip() or None,
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'wheel': data})
        messages.success(request, 'Progreso registrado.')
    except (ValueError, SalesDecisionDef.DoesNotExist) as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)
        messages.error(request, str(e))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error: {e}')
    return redirect(
        f"{reverse('store:managers_dashboard')}"
        f"?year={request.POST.get('year')}&month={request.POST.get('month')}"
    )


@staff_member_required
@require_POST
def managers_decision_undo(request):
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')
    try:
        decision_id = int(request.POST.get('decision_id') or 0)
        year = int(request.POST.get('year') or timezone.localdate().year)
        month = int(request.POST.get('month') or timezone.localdate().month)
        day = int(request.POST.get('day') or timezone.localdate().day)
        activity_date = date_cls(year, month, day)
        data = undo_last_log(
            user=request.user,
            decision_id=decision_id,
            activity_date=activity_date,
            year=year,
            month=month,
            as_admin=request.user.is_superuser,
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'wheel': data})
        messages.info(request, 'Último registro deshecho.')
    except (ValueError, PermissionError) as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)
        messages.error(request, str(e))
    return redirect(
        f"{reverse('store:managers_dashboard')}"
        f"?year={request.POST.get('year')}&month={request.POST.get('month')}"
    )

@staff_member_required
def managers_activities(request):
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')

    today = timezone.localdate()
    ensure_today_instances(request.user, today)

    status = (request.GET.get('status') or '').strip()
    category = (request.GET.get('category') or '').strip()
    scope = (request.GET.get('scope') or 'week').strip()

    qs = (
        ActivityInstance.objects
        .filter(assignee=request.user)
        .select_related('template', 'template__category', 'validated_by')
        .order_by('-due_date', '-id')
    )
    w_start = week_start(today)
    if scope == 'today':
        qs = qs.filter(Q(period_key=today.isoformat()) | Q(due_date=today))
    elif scope == 'week':
        qs = qs.filter(
            Q(due_date__gte=w_start, due_date__lte=w_start + timedelta(days=6))
            | Q(period_key=week_key(today))
            | Q(period_key=today.isoformat())
        )

    if status == 'pending':
        qs = qs.filter(status__in=('pending', 'in_progress'))
    elif status == 'completed':
        qs = qs.filter(status='validated')
    elif status == 'review':
        qs = qs.filter(status='pending_validation')
    elif status == 'expired':
        qs = qs.filter(status='expired')
    elif status == 'rejected':
        qs = qs.filter(status='rejected')

    if category:
        qs = qs.filter(template__category__slug=category)

    categories = ActivityCategory.objects.filter(is_active=True).order_by('order')
    return render(request, 'store/managers/activities.html', {
        'profile': profile,
        'activities': qs[:200],
        'categories': categories,
        'filter_status': status,
        'filter_category': category,
        'filter_scope': scope,
        'today': today,
    })


@staff_member_required
def managers_activity_detail(request, activity_id):
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')

    activity = get_object_or_404(
        ActivityInstance.objects.select_related(
            'template', 'template__category', 'assignee', 'validated_by', 'related_quotation',
        ),
        id=activity_id,
    )
    is_owner = activity.assignee_id == request.user.id
    is_admin = request.user.is_superuser or request.user.is_staff
    if not is_owner and not is_admin:
        return HttpResponseForbidden('Sin permiso.')

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'start' and is_owner and activity.status == 'pending':
                activity.status = 'in_progress'
                activity.started_at = timezone.now()
                activity.save(update_fields=['status', 'started_at', 'updated_at'])
                messages.success(request, 'Actividad en progreso.')
            elif action == 'complete' and is_owner:
                submit_activity_completion(
                    instance=activity,
                    user=request.user,
                    notes=request.POST.get('notes') or '',
                    evidence=request.FILES.get('evidence'),
                    quotation_id=int(request.POST['quotation_id']) if request.POST.get('quotation_id') else None,
                )
                messages.success(request, 'Actividad registrada.')
            elif action == 'approve' and is_admin:
                validate_activity(
                    instance=activity,
                    validator=request.user,
                    approve=True,
                    notes=request.POST.get('admin_notes') or '',
                )
                messages.success(request, 'Actividad validada y puntos acreditados.')
            elif action == 'reject' and is_admin:
                validate_activity(
                    instance=activity,
                    validator=request.user,
                    approve=False,
                    notes=request.POST.get('admin_notes') or '',
                )
                messages.warning(request, 'Actividad rechazada.')
            else:
                messages.error(request, 'Acción no permitida.')
        except (ValueError, PermissionError) as e:
            messages.error(request, str(e))
        return redirect('store:managers_activity_detail', activity_id=activity.id)

    entries = PointLedger.objects.filter(activity=activity).order_by('-created_at')
    return render(request, 'store/managers/activity_detail.html', {
        'profile': profile,
        'activity': activity,
        'is_owner': is_owner,
        'is_admin': is_admin,
        'entries': entries,
    })


@staff_member_required
def managers_results(request):
    profile = _require_manager(request)
    if profile is None:
        return HttpResponseForbidden('Acceso solo para staff.')

    today = timezone.localdate()
    scope = (request.GET.get('scope') or 'week').strip()
    if scope == 'month':
        start = today.replace(day=1)
        end = today
    else:
        start = week_start(today)
        end = start + timedelta(days=6)

    # Managers solo ven sus resultados; superuser puede filtrar
    target_user = request.user
    manager_id = request.GET.get('manager')
    if request.user.is_superuser and manager_id:
        target_user = get_object_or_404(User, id=manager_id, is_staff=True)

    stats = commercial_stats(target_user, start, end)
    all_stats = commercial_stats(None, start, end) if request.user.is_superuser else None
    managers = User.objects.filter(is_staff=True, is_active=True).order_by('first_name', 'username')

    return render(request, 'store/managers/results.html', {
        'profile': profile,
        'stats': stats,
        'all_stats': all_stats,
        'start': start,
        'end': end,
        'scope': scope,
        'managers': managers,
        'target_user': target_user,
    })


@staff_member_required
def managers_admin(request):
    """Panel admin: plantillas, metas, validaciones pendientes, seed."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Solo administradores.')

    profile = ensure_manager_profile(request.user)
    settings_obj = ManagerSettings.load()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'seed':
                result = seed_default_catalog()
                messages.success(
                    request,
                    f'Catálogo listo: {result["categories"]} categorías, '
                    f'{result["templates_created"]} plantillas nuevas, '
                    f'{result.get("decisions_created", 0)} decisiones clave.',
                )
            elif action == 'save_settings':
                settings_obj.ranking_enabled = request.POST.get('ranking_enabled') == '1'
                settings_obj.default_daily_goal = int(request.POST.get('default_daily_goal') or 20)
                settings_obj.default_weekly_goal = int(request.POST.get('default_weekly_goal') or 100)
                settings_obj.wheel_modality = request.POST.get('wheel_modality') or 'activities'
                if settings_obj.wheel_modality not in ('activities', 'points'):
                    settings_obj.wheel_modality = 'activities'
                settings_obj.wheel_cell_count = max(24, min(400, int(request.POST.get('wheel_cell_count') or 144)))
                settings_obj.wheel_ring_count = max(3, min(10, int(request.POST.get('wheel_ring_count') or 6)))
                settings_obj.wheel_target_points = max(1, int(request.POST.get('wheel_target_points') or 100))
                settings_obj.wheel_max_points = max(1, int(request.POST.get('wheel_max_points') or 144))
                settings_obj.wheel_points_per_cell = max(1, int(request.POST.get('wheel_points_per_cell') or 1))
                settings_obj.wheel_default_period = request.POST.get('wheel_default_period') or 'weekly'
                if settings_obj.wheel_default_period not in ('daily', 'weekly', 'monthly'):
                    settings_obj.wheel_default_period = 'weekly'
                settings_obj.save()
                messages.success(request, 'Configuración de rueda y metas guardada.')
            elif action == 'save_decision':
                did = int(request.POST.get('decision_id') or 0)
                d = get_object_or_404(SalesDecisionDef, id=did)
                d.name = (request.POST.get('name') or d.name).strip()[:160]
                d.short_label = (request.POST.get('short_label') or d.short_label).strip()[:80]
                d.default_target = max(1, int(request.POST.get('default_target') or d.default_target))
                d.points_per_unit = max(0, int(request.POST.get('points_per_unit') or 0))
                d.period_kind = request.POST.get('period_kind') or d.period_kind
                d.every_n_days = max(1, int(request.POST.get('every_n_days') or 1))
                d.color = (request.POST.get('color') or d.color)[:20]
                d.role_filter = (request.POST.get('role_filter') or '').strip()[:80]
                d.is_active = request.POST.get('is_active') == '1'
                d.save()
                messages.success(request, f'Decisión «{d.short_label or d.name}» actualizada.')
            elif action == 'save_manager_decision_goal':
                uid = int(request.POST.get('user_id'))
                did = int(request.POST.get('decision_id'))
                target = max(1, int(request.POST.get('target') or 1))
                ManagerDecisionGoal.objects.update_or_create(
                    manager_id=uid,
                    decision_id=did,
                    defaults={'target': target},
                )
                messages.success(request, 'Meta personalizada guardada.')
            elif action == 'save_goals':
                uid = int(request.POST.get('user_id'))
                p = ensure_manager_profile(get_object_or_404(User, id=uid, is_staff=True))
                p.daily_goal_points = int(request.POST.get('daily_goal') or 20)
                p.weekly_goal_points = int(request.POST.get('weekly_goal') or 100)
                p.role_label = (request.POST.get('role_label') or p.role_label)[:80]
                p.is_active = request.POST.get('is_active') == '1'
                p.save()
                messages.success(request, f'Metas de {p.get_display_name()} actualizadas.')
            elif action == 'toggle_template':
                tpl = get_object_or_404(ActivityTemplate, id=int(request.POST.get('template_id')))
                tpl.is_active = not tpl.is_active
                tpl.save(update_fields=['is_active', 'updated_at'])
                messages.success(request, f'Plantilla «{tpl.name}» {"activada" if tpl.is_active else "desactivada"}.')
            elif action == 'update_points':
                tpl = get_object_or_404(ActivityTemplate, id=int(request.POST.get('template_id')))
                tpl.points = max(1, int(request.POST.get('points') or tpl.points))
                tpl.daily_limit = max(0, int(request.POST.get('daily_limit') or tpl.daily_limit))
                tpl.requires_evidence = request.POST.get('requires_evidence') == '1'
                tpl.requires_validation = request.POST.get('requires_validation') == '1'
                tpl.save()
                messages.success(request, f'Puntos de «{tpl.name}» actualizados.')
            elif action == 'adjust_points':
                uid = int(request.POST.get('user_id'))
                pts = int(request.POST.get('points') or 0)
                reason = (request.POST.get('reason') or '').strip()
                adjust_points(
                    manager=get_object_or_404(User, id=uid, is_staff=True),
                    points=pts,
                    reason=reason or 'Ajuste admin',
                    created_by=request.user,
                )
                messages.success(request, 'Ajuste de puntos registrado en el ledger.')
            else:
                messages.error(request, 'Acción desconocida.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
        return redirect('store:managers_admin')

    pending_review = (
        ActivityInstance.objects
        .filter(status='pending_validation')
        .select_related('assignee', 'template')
        .order_by('completed_at')[:50]
    )
    templates = (
        ActivityTemplate.objects
        .select_related('category')
        .order_by('category__order', 'order', 'name')
    )
    profiles = ManagerProfile.objects.select_related('user').order_by('display_name')
    decisions = list(SalesDecisionDef.objects.order_by('order', 'id'))
    decision_goals = list(
        ManagerDecisionGoal.objects.select_related('manager', 'decision').order_by('manager_id', 'decision__order')
    )
    if not ActivityTemplate.objects.exists() and not SalesDecisionDef.objects.exists():
        seed_hint = True
    else:
        seed_hint = False

    return render(request, 'store/managers/admin.html', {
        'profile': profile,
        'settings_obj': settings_obj,
        'pending_review': pending_review,
        'templates': templates,
        'profiles': profiles,
        'decisions': decisions,
        'decision_goals': decision_goals,
        'seed_hint': seed_hint,
        'categories': ActivityCategory.objects.order_by('order'),
    })


@staff_member_required
@require_POST
def managers_quick_complete(request, activity_id):
    activity = get_object_or_404(ActivityInstance, id=activity_id, assignee=request.user)
    try:
        submit_activity_completion(
            instance=activity,
            user=request.user,
            notes=request.POST.get('notes') or '',
            evidence=request.FILES.get('evidence'),
        )
        messages.success(request, f'«{activity.title}» registrada.')
    except (ValueError, PermissionError) as e:
        messages.error(request, str(e))
    next_url = request.POST.get('next') or reverse('store:managers_dashboard')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect('store:managers_dashboard')
