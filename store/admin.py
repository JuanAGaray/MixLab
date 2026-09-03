from django.contrib import admin
from .models import EventLandingLead
from .dian.models import DianElectronicInvoice, DianHabilitacionBatch, DianHabilitacionDocument, DianInvoiceSequence, DianSubmissionLog


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
