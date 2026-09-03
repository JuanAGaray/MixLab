"""Configuración DIAN desde Django settings."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class DianConfig:
    environment: str
    software_id: str
    software_pin: str
    prefix: str
    range_from: int
    range_to: int
    technical_key: str
    certificate_path: str
    certificate_password: str
    certificate_base64: str
    auto_emit_on_payment: bool
    ws_url_habilitacion: str
    ws_url_produccion: str
    qr_url_habilitacion: str
    qr_url_produccion: str
    resolution_number: str
    resolution_from: str
    resolution_to: str
    test_set_id: str
    hab_invoices: int
    hab_credit_notes: int
    hab_debit_notes: int

    @property
    def hab_total_documents(self) -> int:
        return self.hab_invoices + self.hab_credit_notes + self.hab_debit_notes

    @property
    def is_habilitacion(self) -> bool:
        return self.environment.upper() in ('HABILITACION', 'HAB', 'TEST', '2')

    @property
    def profile_execution_id(self) -> str:
        """1=producción, 2=habilitación."""
        return '2' if self.is_habilitacion else '1'

    @property
    def environment_type_code(self) -> str:
        return self.profile_execution_id

    @property
    def ws_url(self) -> str:
        return self.ws_url_habilitacion if self.is_habilitacion else self.ws_url_produccion

    @property
    def qr_base_url(self) -> str:
        return self.qr_url_habilitacion if self.is_habilitacion else self.qr_url_produccion

    @property
    def has_certificate(self) -> bool:
        return bool(self.certificate_path or self.certificate_base64)


def get_dian_config() -> DianConfig:
    return DianConfig(
        environment=getattr(settings, 'DIAN_ENVIRONMENT', 'HABILITACION'),
        software_id=getattr(settings, 'DIAN_SOFTWARE_ID', ''),
        software_pin=getattr(settings, 'DIAN_SOFTWARE_PIN', ''),
        prefix=getattr(settings, 'DIAN_TEST_PREFIX', 'SETP'),
        range_from=int(getattr(settings, 'DIAN_TEST_FROM', 990000000)),
        range_to=int(getattr(settings, 'DIAN_TEST_TO', 995000000)),
        technical_key=getattr(settings, 'DIAN_TEST_TECHNICAL_KEY', ''),
        certificate_path=getattr(settings, 'DIAN_CERTIFICATE_PATH', ''),
        certificate_password=getattr(settings, 'DIAN_CERTIFICATE_PASSWORD', ''),
        certificate_base64=getattr(settings, 'DIAN_CERTIFICATE_BASE64', ''),
        auto_emit_on_payment=bool(getattr(settings, 'DIAN_AUTO_EMIT_ON_PAYMENT', False)),
        ws_url_habilitacion=getattr(
            settings,
            'DIAN_WS_URL_HABILITACION',
            'https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc',
        ),
        ws_url_produccion=getattr(
            settings,
            'DIAN_WS_URL_PRODUCCION',
            'https://vpfe.dian.gov.co/WcfDianCustomerServices.svc',
        ),
        qr_url_habilitacion=getattr(
            settings,
            'DIAN_QR_URL_HABILITACION',
            'https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=',
        ),
        qr_url_produccion=getattr(
            settings,
            'DIAN_QR_URL_PRODUCCION',
            'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=',
        ),
        resolution_number=getattr(settings, 'DIAN_RESOLUTION_NUMBER', '18760000001'),
        resolution_from=getattr(settings, 'DIAN_RESOLUTION_FROM', '2019-01-19'),
        resolution_to=getattr(settings, 'DIAN_RESOLUTION_TO', '2030-01-19'),
        test_set_id=getattr(settings, 'DIAN_TEST_SET_ID', ''),
        hab_invoices=int(getattr(settings, 'DIAN_HAB_INVOICES', 30)),
        hab_credit_notes=int(getattr(settings, 'DIAN_HAB_CREDIT_NOTES', 10)),
        hab_debit_notes=int(getattr(settings, 'DIAN_HAB_DEBIT_NOTES', 10)),
    )


def is_habilitacion() -> bool:
    return get_dian_config().is_habilitacion
