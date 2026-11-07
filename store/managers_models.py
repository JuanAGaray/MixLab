"""
MixLab Managers — ejecución, productividad y puntuación.
Modelos importados desde store.models para migraciones de la app store.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class ManagerProfile(models.Model):
    """Perfil de ejecución para staff (admins / sales)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manager_profile',
        verbose_name='Usuario',
    )
    display_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Nombre en tablero')
    role_label = models.CharField(max_length=80, blank=True, default='Manager', verbose_name='Cargo')
    daily_goal_points = models.PositiveIntegerField(default=20, verbose_name='Meta diaria (pts)')
    weekly_goal_points = models.PositiveIntegerField(default=100, verbose_name='Meta semanal (pts)')
    is_active = models.BooleanField(default=True, verbose_name='Activo en Managers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil Manager'
        verbose_name_plural = 'Perfiles Manager'
        ordering = ['display_name', 'user__username']

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self) -> str:
        if (self.display_name or '').strip():
            return self.display_name.strip()
        u = self.user
        full = (u.get_full_name() or '').strip()
        return full or u.username


class ManagerSettings(models.Model):
    """Configuración singleton del módulo Managers."""

    ranking_enabled = models.BooleanField(default=True, verbose_name='Mostrar ranking')
    default_daily_goal = models.PositiveIntegerField(default=20)
    default_weekly_goal = models.PositiveIntegerField(default=100)
    # Rueda de decisiones
    wheel_modality = models.CharField(
        max_length=16,
        default='activities',
        choices=[
            ('activities', 'Cumplimiento de actividades'),
            ('points', 'Puntuación acumulada'),
        ],
    )
    wheel_cell_count = models.PositiveIntegerField(default=144)
    wheel_ring_count = models.PositiveIntegerField(default=6)
    wheel_target_points = models.PositiveIntegerField(default=100)
    wheel_max_points = models.PositiveIntegerField(default=144)
    wheel_points_per_cell = models.PositiveIntegerField(default=1)
    wheel_default_period = models.CharField(
        max_length=16,
        default='weekly',
        choices=[
            ('daily', 'Diario'),
            ('weekly', 'Semanal'),
            ('monthly', 'Mensual'),
        ],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración Managers'
        verbose_name_plural = 'Configuración Managers'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ActivityCategory(models.Model):
    CATEGORY_SLUGS = (
        ('ventas', 'Ventas'),
        ('marketing', 'Marketing'),
        ('alianzas', 'Alianzas'),
        ('operaciones', 'Operaciones'),
        ('gestion', 'Gestión'),
    )

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True, default='')
    color = models.CharField(max_length=20, default='#0F6FFF')
    icon = models.CharField(max_length=40, default='bi-lightning-charge')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Categoría de ejecución'
        verbose_name_plural = 'Categorías de ejecución'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class ActivityTemplate(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Diaria'),
        ('weekly', 'Semanal'),
        ('once', 'Única / bajo demanda'),
    ]

    category = models.ForeignKey(
        ActivityCategory,
        on_delete=models.PROTECT,
        related_name='templates',
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default='')
    points = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1)])
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    daily_limit = models.PositiveIntegerField(
        default=1,
        help_text='Máximo de veces que otorga puntos por día (0 = sin límite práctico alto).',
    )
    requires_evidence = models.BooleanField(default=False)
    requires_validation = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_priority = models.BooleanField(default=False, verbose_name='Prioritaria')
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plantilla de actividad'
        verbose_name_plural = 'Plantillas de actividad'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.name} ({self.points} pts)'


class ActivityInstance(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('in_progress', 'En progreso'),
        ('completed', 'Completada'),
        ('pending_validation', 'En revisión'),
        ('validated', 'Validada'),
        ('rejected', 'Rechazada'),
        ('expired', 'Vencida'),
    ]

    template = models.ForeignKey(
        ActivityTemplate,
        on_delete=models.PROTECT,
        related_name='instances',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manager_activities',
    )
    period_key = models.CharField(
        max_length=32,
        help_text='Clave de periodo (YYYY-MM-DD o YYYY-Www) para evitar duplicados recurrentes.',
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='pending')
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default='')
    manager_notes = models.TextField(blank=True, default='')
    admin_notes = models.TextField(blank=True, default='')
    points_possible = models.PositiveIntegerField(default=0)
    points_awarded = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manager_validations',
    )
    evidence = models.FileField(
        upload_to='managers/evidence/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Evidencia',
    )
    related_quotation = models.ForeignKey(
        'store.Quotation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manager_activities',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Actividad asignada'
        verbose_name_plural = 'Actividades asignadas'
        ordering = ['-due_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'assignee', 'period_key'],
                name='uniq_manager_activity_period',
            ),
        ]
        indexes = [
            models.Index(fields=['assignee', 'status', 'due_date']),
            models.Index(fields=['period_key', 'assignee']),
        ]

    def __str__(self):
        return f'{self.title} · {self.assignee_id} · {self.period_key}'

    @property
    def status_color(self) -> str:
        return {
            'pending': 'gray',
            'in_progress': 'blue',
            'completed': 'yellow',
            'pending_validation': 'yellow',
            'validated': 'green',
            'rejected': 'red',
            'expired': 'red',
        }.get(self.status, 'gray')


class PointLedger(models.Model):
    """Historial inmutable de puntos (créditos y ajustes)."""

    ENTRY_CHOICES = [
        ('earn', 'Ganancia'),
        ('adjust', 'Ajuste'),
        ('revoke', 'Revocación'),
    ]

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='point_ledger',
    )
    activity = models.ForeignKey(
        ActivityInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='point_entries',
    )
    entry_type = models.CharField(max_length=16, choices=ENTRY_CHOICES, default='earn')
    points = models.IntegerField(help_text='Positivo = crédito; negativo = ajuste/revocación')
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='point_ledger_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Idempotencia: evita doble acreditación al refrescar
    idempotency_key = models.CharField(max_length=80, unique=True)

    class Meta:
        verbose_name = 'Movimiento de puntos'
        verbose_name_plural = 'Movimientos de puntos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.manager_id}: {self.points} ({self.entry_type})'


class ManagerWeekSnapshot(models.Model):
    """Resumen semanal de rendimiento (historial)."""

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manager_week_snapshots',
    )
    week_key = models.CharField(max_length=16)  # YYYY-Www
    week_start = models.DateField()
    target_points = models.PositiveIntegerField(default=100)
    earned_points = models.IntegerField(default=0)
    activities_done = models.PositiveIntegerField(default=0)
    activities_total = models.PositiveIntegerField(default=0)
    quotations_count = models.PositiveIntegerField(default=0)
    sales_count = models.PositiveIntegerField(default=0)
    sales_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Snapshot semanal Manager'
        verbose_name_plural = 'Snapshots semanales Manager'
        constraints = [
            models.UniqueConstraint(fields=['manager', 'week_key'], name='uniq_manager_week_snapshot'),
        ]
        ordering = ['-week_start']

    def __str__(self):
        return f'{self.manager_id} · {self.week_key}'

    @property
    def compliance_pct(self) -> float:
        if not self.target_points:
            return 0.0
        return min(100.0, round(100.0 * max(0, self.earned_points) / self.target_points, 1))


# ——— Rueda de 8 decisiones clave de venta ———


class SalesDecisionDef(models.Model):
    """Plantilla de una de las 8 decisiones clave (configurable)."""

    PERIOD_CHOICES = [
        ('daily', 'Diaria'),
        ('every_n_days', 'Cada N días'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    short_label = models.CharField(max_length=80, blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    default_target = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    period_kind = models.CharField(max_length=20, choices=PERIOD_CHOICES, default='daily')
    every_n_days = models.PositiveIntegerField(default=1)
    points_per_unit = models.PositiveIntegerField(default=1)
    is_score_goal = models.BooleanField(
        default=False,
        help_text='Si es True, la meta es de puntuación acumulada (decisión 8).',
    )
    is_active = models.BooleanField(default=True)
    color = models.CharField(max_length=20, default='#f97316')
    role_filter = models.CharField(
        max_length=80,
        blank=True,
        default='',
        help_text='Vacío = todos. Si se define, solo managers con ese role_label.',
    )

    class Meta:
        verbose_name = 'Decisión clave de venta'
        verbose_name_plural = 'Decisiones clave de venta'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.order}. {self.name}'


class ManagerDecisionGoal(models.Model):
    """Meta personalizada por manager (sobrescribe default_target)."""

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sales_decision_goals',
    )
    decision = models.ForeignKey(
        SalesDecisionDef,
        on_delete=models.CASCADE,
        related_name='manager_goals',
    )
    target = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Meta de decisión por manager'
        verbose_name_plural = 'Metas de decisión por manager'
        constraints = [
            models.UniqueConstraint(fields=['manager', 'decision'], name='uniq_manager_decision_goal'),
        ]

    def __str__(self):
        return f'{self.manager_id} · {self.decision.code} = {self.target}'


class SalesWheelBoard(models.Model):
    """Rueda de un manager en un periodo concreto (historial)."""

    PERIOD_CHOICES = [
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]
    MODALITY_CHOICES = [
        ('activities', 'Cumplimiento de actividades'),
        ('points', 'Puntuación acumulada'),
    ]

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sales_wheels',
    )
    period_type = models.CharField(max_length=16, choices=PERIOD_CHOICES, default='weekly')
    period_key = models.CharField(max_length=24)
    period_start = models.DateField()
    period_end = models.DateField()
    modality = models.CharField(max_length=16, choices=MODALITY_CHOICES, default='activities')
    cell_count = models.PositiveIntegerField(default=144)
    ring_count = models.PositiveIntegerField(default=6)
    target_points = models.PositiveIntegerField(default=100)
    max_points = models.PositiveIntegerField(default=120)
    points_per_cell = models.PositiveIntegerField(default=1)
    points_earned = models.IntegerField(default=0)
    cells_filled = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Rueda de ventas'
        verbose_name_plural = 'Ruedas de ventas'
        constraints = [
            models.UniqueConstraint(
                fields=['manager', 'period_type', 'period_key'],
                name='uniq_sales_wheel_period',
            ),
        ]
        ordering = ['-period_start']

    def __str__(self):
        return f'Rueda {self.manager_id} · {self.period_key}'

    @property
    def compliance_pct(self) -> float:
        goal = self.target_points or 1
        return min(100.0, round(100.0 * max(0, self.points_earned) / goal, 1))

    @property
    def cells_pct(self) -> float:
        if not self.cell_count:
            return 0.0
        return min(100.0, round(100.0 * self.cells_filled / self.cell_count, 1))


class SalesDecisionProgress(models.Model):
    """Progreso de una decisión dentro de una rueda/periodo."""

    board = models.ForeignKey(
        SalesWheelBoard,
        on_delete=models.CASCADE,
        related_name='decision_progress',
    )
    decision = models.ForeignKey(
        SalesDecisionDef,
        on_delete=models.PROTECT,
        related_name='progress_rows',
    )
    target = models.PositiveIntegerField(default=1)
    current = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Progreso de decisión'
        verbose_name_plural = 'Progresos de decisión'
        constraints = [
            models.UniqueConstraint(fields=['board', 'decision'], name='uniq_board_decision_progress'),
        ]

    @property
    def is_done(self) -> bool:
        return self.current >= self.target

    @property
    def pct(self) -> float:
        if not self.target:
            return 0.0
        return min(100.0, round(100.0 * self.current / self.target, 1))


class SalesDecisionLog(models.Model):
    """Cada unidad ejecutada (ej. 1 contacto WhatsApp)."""

    board = models.ForeignKey(
        SalesWheelBoard,
        on_delete=models.CASCADE,
        related_name='logs',
    )
    decision = models.ForeignKey(
        SalesDecisionDef,
        on_delete=models.PROTECT,
        related_name='logs',
    )
    units = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    points_awarded = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, default='')
    # Día comercial al que aplica (independiente de created_at)
    activity_date = models.DateField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_decision_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    undone = models.BooleanField(default=False)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_decision_undos',
    )
    idempotency_key = models.CharField(max_length=80, unique=True)

    class Meta:
        verbose_name = 'Ejecución de decisión'
        verbose_name_plural = 'Ejecuciones de decisión'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['board', 'decision', 'activity_date']),
        ]

    def effective_date(self):
        if self.activity_date:
            return self.activity_date
        return timezone.localtime(self.created_at).date() if self.created_at else timezone.localdate()


class SalesWheelCellMark(models.Model):
    """Casilla marcada en la rueda (legado / puntuación)."""

    board = models.ForeignKey(
        SalesWheelBoard,
        on_delete=models.CASCADE,
        related_name='cell_marks',
    )
    cell_index = models.PositiveIntegerField()
    ring = models.PositiveIntegerField(default=0)
    sector = models.PositiveIntegerField(default=0)
    log = models.ForeignKey(
        SalesDecisionLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cell_marks',
    )
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Casilla de rueda'
        verbose_name_plural = 'Casillas de rueda'
        constraints = [
            models.UniqueConstraint(fields=['board', 'cell_index'], name='uniq_wheel_cell'),
        ]
        ordering = ['cell_index']


class SalesMonthCell(models.Model):
    """Casilla del calendario mensual: decisión × día (vinculada a fecha real)."""

    STATE_CHOICES = [
        ('pending', 'Pendiente'),
        ('progress', 'En progreso'),
        ('done', 'Completado'),
        ('weekend', 'Fin de semana'),
        ('na', 'No aplica'),
    ]

    board = models.ForeignKey(
        SalesWheelBoard,
        on_delete=models.CASCADE,
        related_name='month_cells',
    )
    decision = models.ForeignKey(
        SalesDecisionDef,
        on_delete=models.PROTECT,
        related_name='month_cells',
    )
    day = models.PositiveSmallIntegerField()  # 1–31
    activity_date = models.DateField()
    units = models.PositiveIntegerField(default=0)
    target = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default='pending')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Casilla mensual'
        verbose_name_plural = 'Casillas mensuales'
        constraints = [
            models.UniqueConstraint(
                fields=['board', 'decision', 'day'],
                name='uniq_month_cell_decision_day',
            ),
        ]
        ordering = ['day', 'decision__order']

    def __str__(self):
        return f'{self.board_id} D{self.day} · {self.decision_id} · {self.state}'

    def recompute_state(self):
        if self.state in ('weekend', 'na'):
            return self.state
        if self.units <= 0:
            self.state = 'pending'
        elif self.units >= self.target:
            self.state = 'done'
        else:
            self.state = 'progress'
        return self.state
