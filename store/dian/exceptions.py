"""Excepciones del módulo DIAN."""


class DianError(Exception):
    """Error base de facturación electrónica."""


class DianValidationError(DianError):
    """Datos insuficientes o inválidos para emitir."""


class DianSigningError(DianError):
    """Error al firmar el XML."""


class DianSubmissionError(DianError):
    """Error al enviar o consultar en la DIAN."""
