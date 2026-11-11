from django.contrib import admin
from .models import (
    EventLandingLead,
    FlowDiagram,
    PortfolioAddon,
    PortfolioGalleryImage,
    PortfolioPackage,
    PrepStage,
    QuotationServiceReview,
    ServiceBonusCoupon,
)
from .managers_models import (
    ActivityCategory,
    ActivityInstance,
    ActivityTemplate,
    ManagerDecisionGoal,
    ManagerProfile,
    ManagerSettings,
    PointLedger,
    SalesDecisionDef,
    SalesDecisionLog,
    SalesDecisionProgress,
    SalesMonthCell,
    SalesWheelBoard,
    SalesWheelCellMark,
)
from .dian.models import DianElectronicInvoice, DianHabilitacionBatch, DianHabilitacionDocument, DianInvoiceSequence, DianSubmissionLog


@admin.register(PortfolioPackage)
class PortfolioPackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'price_label', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    list_editable = ('sort_order', 'is_active')


@admin.register(PortfolioGalleryImage)
class PortfolioGalleryImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'caption', 'location', 'event_date', 'sort_order', 'is_active', 'created_at')
    list_filter = ('is_active', 'event_date')
    list_editable = ('sort_order', 'is_active', 'caption', 'location', 'event_date')
    search_fields = ('caption', 'location')
    ordering = ('-event_date', '-created_at')


@admin.register(PortfolioAddon)
class PortfolioAddonAdmin(admin.ModelAdmin):
    list_display = ('title', 'price_label', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    list_editable = ('sort_order', 'is_active')


@admin.register(PrepStage)
class PrepStageAdmin(admin.ModelAdmin):
    list_display = ('title', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    list_editable = ('sort_order', 'is_active')


@admin.register(FlowDiagram)
class FlowDiagramAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'category', 'status', 'sort_order', 'updated_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'slug', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at', 'published_at')


@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'role_label', 'daily_goal_points', 'weekly_goal_points', 'is_active')
    list_filter = ('is_active',)


@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ActivityTemplate)
class ActivityTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'points', 'frequency', 'daily_limit', 'requires_validation', 'is_active')
    list_filter = ('category', 'frequency', 'is_active')


@admin.register(ActivityInstance)
class ActivityInstanceAdmin(admin.ModelAdmin):
    list_display = ('title', 'assignee', 'status', 'period_key', 'points_awarded', 'due_date')
    list_filter = ('status',)
    search_fields = ('title', 'assignee__username')


@admin.register(PointLedger)
class PointLedgerAdmin(admin.ModelAdmin):
    list_display = ('manager', 'points', 'entry_type', 'reason', 'created_at')
    list_filter = ('entry_type',)
    readonly_fields = ('idempotency_key', 'created_at')


@admin.register(ManagerSettings)
class ManagerSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'ranking_enabled', 'default_daily_goal', 'default_weekly_goal',
        'wheel_modality', 'wheel_cell_count', 'wheel_default_period', 'updated_at',
    )


@admin.register(SalesDecisionDef)
class SalesDecisionDefAdmin(admin.ModelAdmin):
    list_display = ('order', 'code', 'short_label', 'default_target', 'points_per_unit', 'period_kind', 'is_active')
    list_editable = ('default_target', 'points_per_unit', 'is_active')
    list_filter = ('is_active', 'period_kind')


@admin.register(ManagerDecisionGoal)
class ManagerDecisionGoalAdmin(admin.ModelAdmin):
    list_display = ('manager', 'decision', 'target')
    list_filter = ('decision',)


@admin.register(SalesWheelBoard)
class SalesWheelBoardAdmin(admin.ModelAdmin):
    list_display = ('manager', 'period_type', 'period_key', 'modality', 'points_earned', 'target_points', 'cells_filled', 'cell_count')
    list_filter = ('period_type', 'modality')


@admin.register(SalesDecisionProgress)
class SalesDecisionProgressAdmin(admin.ModelAdmin):
    list_display = ('board', 'decision', 'current', 'target')


@admin.register(SalesDecisionLog)
class SalesDecisionLogAdmin(admin.ModelAdmin):
    list_display = ('board', 'decision', 'units', 'points_awarded', 'created_at', 'undone')
    list_filter = ('undone', 'decision')
    readonly_fields = ('idempotency_key', 'created_at')


@admin.register(SalesWheelCellMark)
class SalesWheelCellMarkAdmin(admin.ModelAdmin):
    list_display = ('board', 'cell_index', 'ring', 'sector', 'marked_at')


@admin.register(SalesMonthCell)
class SalesMonthCellAdmin(admin.ModelAdmin):
    list_display = ('board', 'decision', 'day', 'activity_date', 'units', 'target', 'state')
    list_filter = ('state', 'decision')


@admin.register(QuotationServiceReview)
class QuotationServiceReviewAdmin(admin.ModelAdmin):
    list_display = (
        'quotation', 'score_operator', 'score_flavors', 'score_recommend',
        'submitted_at', 'link_expires_at',
    )
    list_filter = ('submitted_at',)
    search_fields = ('quotation__id', 'access_code', 'reason')
    readonly_fields = ('access_token', 'created_at', 'updated_at')


@admin.register(ServiceBonusCoupon)
class ServiceBonusCouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount_percent', 'status', 'valid_until',
        'source_quotation', 'redeemed_on_quotation', 'redeemed_at',
    )
    list_filter = ('status',)
    search_fields = ('code', 'created_for_name', 'created_for_phone')
    readonly_fields = ('created_at',)


@admin.register(EventLandingLead)
class EventLandingLeadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'organizer_name',
        'event_type',
        'event_date',
        'guests_count',
        'city',
        'event_place',
        'phone',
        'status',
        'combo',
        'quotation',
        'created_at',
    )
    list_filter = ('status', 'event_type', 'city', 'created_at')
    search_fields = ('organizer_name', 'phone', 'email', 'city', 'event_place', 'notes', 'staff_notes')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('combo', 'quotation')
    list_editable = ('status',)


@admin.register(DianElectronicInvoice)
class DianElectronicInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'quotation', 'status', 'total_amount', 'issue_date', 'created_at')
    list_filter = ('status', 'environment')
    search_fields = ('invoice_number', 'cufe', 'quotation__id')
    readonly_fields = ('cufe', 'qr_url', 'created_at', 'updated_at')


@admin.register(DianInvoiceSequence)
class DianInvoiceSequenceAdmin(admin.ModelAdmin):
    list_display = ('prefix', 'current', 'range_from', 'range_to', 'updated_at')


@admin.register(DianSubmissionLog)
class DianSubmissionLogAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'action', 'success', 'created_at')
    list_filter = ('success', 'action')


@admin.register(DianHabilitacionBatch)
class DianHabilitacionBatchAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status', 'invoice_count', 'credit_note_count',
        'debit_note_count', 'dian_track_id', 'created_at',
    )
    list_filter = ('status',)


@admin.register(DianHabilitacionDocument)
class DianHabilitacionDocumentAdmin(admin.ModelAdmin):
    list_display = ('document_number', 'doc_type', 'batch', 'consecutive', 'created_at')
    list_filter = ('doc_type',)
