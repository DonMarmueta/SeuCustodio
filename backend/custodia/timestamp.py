"""Datação das evidências em UTC e horário de Brasília.

Mantém compatibilidade com o padrão já usado pela CyberMarmouts
(converter_timestamps_brasilia.py), produzindo sempre os dois fusos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.config import TIMEZONE_BR

_BR_TZ = ZoneInfo(TIMEZONE_BR)


def agora() -> dict:
    """Retorna o instante atual em UTC e Brasília (ISO 8601)."""
    dt_utc = datetime.now(timezone.utc)
    dt_br = dt_utc.astimezone(_BR_TZ)
    return {
        "utc": dt_utc.isoformat(),
        "brasilia": dt_br.isoformat(),
        "epoch": dt_utc.timestamp(),
    }


def converter_unix(valor: int | float, unidade: str = "ms") -> dict:
    """Converte um timestamp Unix (de metadados de posts) para UTC + Brasília.

    :param valor: timestamp Unix.
    :param unidade: 'ms' para milissegundos, 's' para segundos.
    """
    if unidade == "ms":
        segundos = valor / 1000.0
    elif unidade == "s":
        segundos = float(valor)
    else:
        raise ValueError("unidade deve ser 'ms' ou 's'.")

    dt_utc = datetime.fromtimestamp(segundos, tz=timezone.utc)
    dt_br = dt_utc.astimezone(_BR_TZ)
    return {
        "original": valor,
        "unidade": unidade,
        "utc": dt_utc.isoformat(),
        "brasilia": dt_br.isoformat(),
    }
