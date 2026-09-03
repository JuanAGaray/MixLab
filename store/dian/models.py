"""Modelos de facturación electrónica DIAN."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class DianInvoiceSequence(models.Model):
    """Singleton de numeración autorizada (SETP en habilitación)."""

    prefix = models.CharField(max_length=10, default='SETP', verbose_name='Prefijo')
    range_from = models.PositiveBigIntegerField(default=990000000, verbose_name='Desde')
    range_to = models.PositiveBigIntegerField(default=995000000, verbose_name='Hasta')
    current = models.PositiveBigIntegerField(default=989999999, verbose_name='Último consecutivo')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Numeración DIAN'
        verbose_name_plural = 'Numeración DIAN'

    def __str__(self):
        return f'{self.prefix}{self.current} ({self.range_from}–{self.range_to})'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class DianElectronicInvoice(models.Model):
    """Factura electrónica emitida desde una cotización."""

    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('xml_generated', 'XML generado'),
        ('signed', 'Firmado'),
        ('submitted', 'Enviado a DIAN'),
        ('accepted', 'Aceptado DIAN'),
        ('rejected', 'Rechazado DIAN'),
        ('error', 'Error'),
    ]

    quotation = models.OneToOneField(
        'store.Quotation',
        on_delete=models.PROTECT,
        related_name='dian_invoice',
        verbose_name='Cotización',
    )
    prefix = models.CharField(max_length=10, verbose_name='Prefijo')
    consecutive = models.PositiveBigIntegerField(verbose_name='Consecutivo')
    invoice_number = models.CharField(max_length=30, unique=True, verbose_name='Número de factura')
    environment = models.CharField(max_length=20, default='HABILITACION', verbose_name='Ambiente')

    issue_date = models.DateField(verbose_name='Fecha emisión')
    issue_time = models.TimeField(verbose_name='Hora emisión')
    cufe = models.CharField(max_length=96, blank=True, default='', verbose_name='CUFE')
    qr_url = models.URLField(max_length=500, blank=True, default='', verbose_name='URL QR')

    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    iva_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    xml_unsigned = models.TextField(blank=True, default='', verbose_name='XML sin firmar')
    xml_signed = models.FileField(
        upload_to='dian/invoices/xml/',
        blank=True,
        null=True,
        verbose_name='XML firmado',
    )
    pdf_file = models.FileField(
        upload_to='dian/invoices/pdf/',
        blank=True,
        null=True,
        verbose_name='PDF representación gráfica',
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    dian_track_id = models.CharField(max_length=120, blank=True, default='', verbose_name='Track ID DIAN')
    dian_status_code = models.CharField(max_length=20, blank=True, default='')
    dian_status_message = models.TextField(blank=True, default='')
    dian_response_raw = models.TextField(blank=True, default='')

    software_id = models.CharField(max_length=120, blank=True, default='')
    technical_key = models.CharField(max_length=64, blank=True, default='')

    emitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dian_invoices_emitted',
        verbose_name='Emitida por',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Factura electrónica DIAN'
        verbose_name_plural = 'Facturas electrónicas DIAN'
        ordering = ['-created_at']

    def __str__(self):
        return f'FE {self.invoice_number} (Cot. #{self.quotation_id})'

    @property
    def is_accepted(self) -> bool:
        return self.status == 'accepted'

    @property
    def can_retry(self) -> bool:
        return self.status in ('error', 'rejected', 'signed', 'xml_generated', 'submitted')


class DianSubmissionLog(models.Model):
    """Auditoría de llamadas al webservice DIAN."""

    invoice = models.ForeignKey(
        DianElectronicInvoice,
        on_delete=models.CASCADE,
        related_name='submission_logs',
        verbose_name='Factura',
    )
    action = models.CharField(max_length=60, verbose_name='Acción')
    request_summary = models.TextField(blank=True, default='')
    response_summary = models.TextField(blank=True, default='')
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log envío DIAN'
        verbose_name_plural = 'Logs envío DIAN'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} · FE {self.invoice.invoice_number}'


class DianHabilitacionBatch(models.Model):
    """Lote de documentos para habilitación SETP."""

    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('signed', 'Firmado'),
        ('zipped', 'ZIP listo'),
        ('submitted', 'Enviado DIAN'),
        ('accepted', 'Aceptado DIAN'),
        ('rejected', 'Rechazado'),
        ('error', 'Error'),
    ]

    test_set_id = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    zip_file = models.FileField(upload_to='dian/habilitacion/zips/', blank=True, null=True)
    dian_track_id = models.CharField(max_length=120, blank=True, default='')
    dian_response = models.TextField(blank=True, default='')
    invoice_count = models.PositiveSmallIntegerField(default=0)
    credit_note_count = models.PositiveSmallIntegerField(default=0)
    debit_note_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lote habilitación DIAN'
        verbose_name_plural = 'Lotes habilitación DIAN'
        ordering = ['-created_at']

    def __str__(self):
        return f'Habilitación {self.pk} · {self.get_status_display()}'


class DianHabilitacionDocument(models.Model):
    """Documento individual del set de habilitación."""

    DOC_TYPES = [
        ('invoice', 'Factura'),
        ('credit_note', 'Nota crédito'),
        ('debit_note', 'Nota débito'),
    ]

    batch = models.ForeignKey(
        DianHabilitacionBatch,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    document_number = models.CharField(max_length=30)
    consecutive = models.PositiveBigIntegerField()
    cufe_cude = models.CharField(max_length=96, blank=True, default='')
    reference_number = models.CharField(max_length=30, blank=True, default='')
    reference_cufe = models.CharField(max_length=96, blank=True, default='')
    xml_unsigned = models.TextField(blank=True, default='')
    xml_signed = models.FileField(upload_to='dian/habilitacion/xml/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento habilitación'
        verbose_name_plural = 'Documentos habilitación'
        ordering = ['consecutive']
        unique_together = [('batch', 'document_number')]

    def __str__(self):
        return f'{self.document_number} ({self.get_doc_type_display()})'
