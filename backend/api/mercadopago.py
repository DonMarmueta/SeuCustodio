"""Integração com o Mercado Pago para pagamentos via Pix.

Usa a API REST diretamente (requests), evitando o SDK. Em MODO_SIMULADO (sem
MP_ACCESS_TOKEN configurado), gera um Pix fictício e permite aprovar o pagamento
manualmente — útil para desenvolver e testar o fluxo completo sem credenciais.
"""

from __future__ import annotations

import secrets
import uuid

import requests

from backend.config import BASE_URL, MODO_SIMULADO, MP_ACCESS_TOKEN

_API = "https://api.mercadopago.com"


def criar_pix(valor: float, descricao: str, email_pagador: str, referencia: str) -> dict:
    """Cria um pagamento Pix e devolve dados para exibição ao cliente.

    Retorna: {ok, ref_externa, status, qr_code, qr_code_base64, simulado, erro}
    """
    if MODO_SIMULADO:
        # Pix fictício para testes (não cobra de verdade).
        return {
            "ok": True,
            "simulado": True,
            "ref_externa": f"SIM-{secrets.token_hex(8)}",
            "status": "pendente",
            "qr_code": "00020126SIMULADO-PIX-COPIA-E-COLA-PROVASOCIAL5204000053039865802BR6304ABCD",
            "qr_code_base64": None,
            "erro": None,
        }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }
    payload = {
        "transaction_amount": round(valor, 2),
        "description": descricao,
        "payment_method_id": "pix",
        "external_reference": referencia,
        "notification_url": f"{BASE_URL}/api/pagamentos/webhook",
        "payer": {"email": email_pagador},
    }
    try:
        resp = requests.post(f"{_API}/v1/payments", json=payload, headers=headers, timeout=30)
        dados = resp.json()
        if resp.status_code in (200, 201):
            tx = dados.get("point_of_interaction", {}).get("transaction_data", {})
            return {
                "ok": True,
                "simulado": False,
                "ref_externa": str(dados.get("id")),
                "status": _traduzir_status(dados.get("status")),
                "qr_code": tx.get("qr_code"),
                "qr_code_base64": tx.get("qr_code_base64"),
                "erro": None,
            }
        return {"ok": False, "erro": f"Mercado Pago {resp.status_code}: {dados}"}
    except requests.RequestException as exc:
        return {"ok": False, "erro": f"Falha de rede com Mercado Pago: {exc}"}


def consultar_pagamento(ref_externa: str) -> str | None:
    """Consulta o status atual de um pagamento. Retorna status traduzido ou None."""
    if MODO_SIMULADO:
        return None
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    try:
        resp = requests.get(f"{_API}/v1/payments/{ref_externa}", headers=headers, timeout=30)
        if resp.status_code == 200:
            return _traduzir_status(resp.json().get("status"))
    except requests.RequestException:
        pass
    return None


def _traduzir_status(status_mp: str | None) -> str:
    return {
        "approved": "aprovado",
        "pending": "pendente",
        "in_process": "pendente",
        "rejected": "recusado",
        "cancelled": "cancelado",
        "refunded": "cancelado",
    }.get(status_mp or "", "pendente")
