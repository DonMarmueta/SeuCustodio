"""Rotas de pagamento: webhook do Mercado Pago e aprovação simulada (dev)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api import mercadopago
from backend.api.auth import usuario_atual
from backend.api.db import get_db
from backend.api.jobs import disparar_coleta
from backend.api.models import Coleta, Pagamento, Usuario
from backend.config import MODO_SIMULADO

router = APIRouter(prefix="/api/pagamentos", tags=["pagamentos"])


def _aprovar_e_disparar(db: Session, pagamento: Pagamento) -> None:
    """Marca pagamento como aprovado, a coleta como paga e dispara a captura."""
    pagamento.status = "aprovado"
    coleta = db.get(Coleta, pagamento.coleta_id)
    if coleta and coleta.status == "aguardando_pagamento":
        coleta.status = "pago"
        coleta.pago_em = datetime.now(timezone.utc)
        db.commit()
        disparar_coleta(coleta.id)
    else:
        db.commit()


@router.post("/webhook")
async def webhook_mercadopago(request: Request, db: Session = Depends(get_db)):
    """Recebe notificações do Mercado Pago e confirma o pagamento.

    O Mercado Pago envia o id do pagamento; consultamos a API para confirmar o
    status real (nunca confiamos apenas no payload recebido).
    """
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001
        corpo = {}

    ref = None
    if isinstance(corpo, dict):
        ref = str(corpo.get("data", {}).get("id") or corpo.get("id") or "")
    ref = ref or request.query_params.get("data.id") or request.query_params.get("id")

    if not ref:
        return {"ok": True, "ignorado": "sem referência"}

    pagamento = db.scalars(select(Pagamento).where(Pagamento.ref_externa == str(ref))).first()
    if pagamento is None:
        return {"ok": True, "ignorado": "pagamento não encontrado"}

    status_real = mercadopago.consultar_pagamento(str(ref))
    if status_real == "aprovado" and pagamento.status != "aprovado":
        _aprovar_e_disparar(db, pagamento)
    elif status_real in ("recusado", "cancelado"):
        pagamento.status = status_real
        db.commit()

    return {"ok": True, "status": pagamento.status}


@router.post("/simular-aprovacao/{coleta_id}")
def simular_aprovacao(
    coleta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Apenas em MODO_SIMULADO: aprova o pagamento manualmente para testes."""
    if not MODO_SIMULADO:
        raise HTTPException(status_code=403, detail="Indisponível: pagamentos reais ativos.")

    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")
    if coleta.pagamento is None:
        raise HTTPException(status_code=400, detail="Sem pagamento associado.")

    _aprovar_e_disparar(db, coleta.pagamento)
    return {"ok": True, "status": coleta.status}
