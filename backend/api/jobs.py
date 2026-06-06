"""Execução da coleta em background após confirmação de pagamento.

MVP: usa uma thread por job. Em produção (Fase 5), trocar por uma fila real
(Celery/RQ + Redis) para resiliência, retry e escala.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from backend.api.db import SessionLocal
from backend.api.models import Coleta
from backend.coletor import coletar
from backend.config import ANALISTA_PADRAO


def disparar_coleta(coleta_id: int) -> None:
    """Inicia a coleta em uma thread separada (não bloqueia o webhook/HTTP)."""
    t = threading.Thread(target=_executar, args=(coleta_id,), daemon=True)
    t.start()


def _executar(coleta_id: int) -> None:
    db = SessionLocal()
    try:
        coleta = db.get(Coleta, coleta_id)
        if coleta is None or coleta.status not in ("pago",):
            return

        coleta.status = "capturando"
        db.commit()

        try:
            resultado = coletar(
                url=coleta.url_alvo,
                analista=ANALISTA_PADRAO,
                caso=f"coleta-{coleta_id}",
                evidencia=None,
                comentario_alvo=coleta.comentario_alvo,
                modo_pericial=coleta.nivel == "pericial",
            )
            coleta.status = "concluido"
            coleta.codigo_verificacao = resultado["codigo"]
            coleta.pasta = resultado["pasta"]
            coleta.hash_manifesto = resultado["manifesto"]["hash_manifesto"]
            coleta.capturado_em = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            coleta.status = "erro"
            coleta.erro_msg = str(exc)
        db.commit()
    finally:
        db.close()
