"""Convierte montos COP a letras (formato cuenta de cobro Colombia)."""
from decimal import Decimal, ROUND_DOWN


_UNIDADES = (
    '', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE',
    'DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE',
    'DIECIOCHO', 'DIECINUEVE', 'VEINTE', 'VEINTIUNO', 'VEINTIDÓS', 'VEINTITRÉS',
    'VEINTICUATRO', 'VEINTICINCO', 'VEINTISÉIS', 'VEINTISIETE', 'VEINTIOCHO', 'VEINTINUEVE',
)
_DECENAS = (
    '', '', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA',
)
_CENTENAS = (
    '', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS',
    'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS',
)


def _tres_digitos(n: int) -> str:
    if n == 0:
        return ''
    if n == 100:
        return 'CIEN'
    c, resto = divmod(n, 100)
    d, u = divmod(resto, 10)
    partes = []
    if c:
        partes.append(_CENTENAS[c])
    if resto < 30:
        if resto:
            partes.append(_UNIDADES[resto])
    else:
        if d:
            dec = _DECENAS[d]
            if u:
                partes.append(f'{dec} Y {_UNIDADES[u]}')
            else:
                partes.append(dec)
        elif u:
            partes.append(_UNIDADES[u])
    return ' '.join(partes).strip()


def _seccion(n: int, singular: str, plural: str) -> str:
    if n == 0:
        return ''
    if n == 1:
        return singular
    return f'{_tres_digitos(n)} {plural}'


def numero_a_letras_pesos(amount) -> str:
    """Ej: 1250000 -> 'UN MILLÓN DOSCIENTOS CINCUENTA MIL PESOS M/CTE'."""
    try:
        value = Decimal(str(amount or 0)).quantize(Decimal('1'), rounding=ROUND_DOWN)
    except Exception:
        value = Decimal('0')
    entero = int(value)
    if entero == 0:
        return 'CERO PESOS M/CTE'
    if entero == 1:
        return 'UN PESO M/CTE'

    millones, resto = divmod(entero, 1_000_000)
    miles, unidades = divmod(resto, 1_000)

    partes = []
    if millones:
        if millones == 1:
            partes.append('UN MILLÓN')
        else:
            partes.append(f'{_tres_digitos(millones)} MILLONES')
    if miles:
        if miles == 1:
            partes.append('MIL')
        else:
            partes.append(f'{_tres_digitos(miles)} MIL')
    if unidades:
        txt = _tres_digitos(unidades)
        if txt:
            partes.append(txt)

    cuerpo = ' '.join(partes).strip()
    return f'{cuerpo} PESOS M/CTE'
