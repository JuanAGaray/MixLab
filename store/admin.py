from django.contrib import admin
from .models import EventLandingLead


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
