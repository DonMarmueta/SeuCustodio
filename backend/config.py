"""Configurações centrais do coletor forense."""

from __future__ import annotations

import os
from pathlib import Path

# Fuso horário oficial para datação das evidências (alinhado ao fluxo da CyberMarmouts).
TIMEZONE_BR = "America/Sao_Paulo"

# Identidade padrão do responsável pela coleta (sobrescrevível via CLI).
ANALISTA_PADRAO = "CyberMarmouts - Inteligência Forense"

# Raiz do projeto (.../Extract) e pasta de saída das evidências.
RAIZ = Path(__file__).resolve().parent.parent
PASTA_EVIDENCIAS = RAIZ / "evidencias"
PASTA_SESSOES = RAIZ / "sessoes"

# User-Agent de navegador real para evitar bloqueios triviais.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Navegador usado pelo Playwright. Se PROVASOCIAL_BROWSER_PATH não for definido,
# tenta usar o Brave instalado no caminho padrão do Windows; se não existir, usa
# o Chromium gerenciado pelo Playwright.
_BRAVE_PADRAO = Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
BROWSER_EXECUTABLE_PATH = os.getenv("PROVASOCIAL_BROWSER_PATH") or (
    str(_BRAVE_PADRAO) if _BRAVE_PADRAO.exists() else None
)

# Timeout padrão (segundos) para requisições e render.
TIMEOUT = int(os.getenv("PROVASOCIAL_TIMEOUT", "30"))

# Verificação de certificado SSL. Mantida LIGADA por padrão (essencial para a
# integridade forense). Em redes com proxy/CA corporativo, aponte um CA bundle
# via PROVASOCIAL_CA_BUNDLE em vez de desligar a verificação.
CA_BUNDLE = os.getenv("PROVASOCIAL_CA_BUNDLE") or None
_verif = os.getenv("PROVASOCIAL_VERIFICAR_SSL", "1").lower()
VERIFICAR_SSL: bool | str = CA_BUNDLE or (_verif not in ("0", "false", "nao", "no"))

# URL base da aplicação (usada em links, webhook e QR de verificação).
BASE_URL = os.getenv("PROVASOCIAL_BASE_URL", "http://localhost:8000")

# URL base do portal público de verificação (vai no QR code do laudo).
PORTAL_VERIFICACAO = os.getenv("PROVASOCIAL_PORTAL", f"{BASE_URL}/verificar")

# Algoritmo de hash usado em toda a cadeia de integridade.
ALGORITMO_HASH = "sha256"

# Sessão autenticada do operador (Playwright storage_state).
# O arquivo contém cookies/tokens e NÃO deve ser versionado ou anexado ao laudo.
STORAGE_STATE_OPERADOR = Path(
    os.getenv("PROVASOCIAL_STORAGE_STATE", str(PASTA_SESSOES / "operador.json"))
)
USAR_SESSAO_OPERADOR = os.getenv("PROVASOCIAL_USAR_SESSAO", "1").lower() not in (
    "0",
    "false",
    "nao",
    "no",
)

# ---------------------------------------------------------------------------
# Camada SaaS (Fase 2)
# ---------------------------------------------------------------------------

# Banco de dados (SQLite por padrão; trocável por Postgres em produção).
DATABASE_URL = os.getenv("PROVASOCIAL_DB", f"sqlite:///{RAIZ / 'provasocial.db'}")

# Chave de assinatura dos tokens de sessão (JWT). TROCAR EM PRODUÇÃO.
SECRET_KEY = os.getenv("PROVASOCIAL_SECRET", "troque-esta-chave-longa-em-producao-com-mais-de-32-bytes")
TOKEN_EXPIRA_HORAS = int(os.getenv("PROVASOCIAL_TOKEN_HORAS", "72"))

# Valor cobrado por captura auditável de publicação (R$).
VALOR_COLETA = float(os.getenv("PROVASOCIAL_VALOR", "9.90"))

# Mercado Pago. Se vazio, a aplicação opera em MODO SIMULADO (sem cobrança real),
# útil para desenvolvimento e testes do fluxo end-to-end.
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MODO_SIMULADO = not bool(MP_ACCESS_TOKEN)

# ---------------------------------------------------------------------------
# Fase 4 — Upsell / produtos complementares
# ---------------------------------------------------------------------------

SERVICOS_ASSESSORIA = {
    "assessoria": {
        "titulo": "Instruções à PAP Seu Custódio",
        "preco": os.getenv("PROVASOCIAL_PRECO_ASSESSORIA", "sob consulta"),
        "descricao": (
            "Documento orientativo que organiza dados do solicitante, contexto narrado, "
            "plataforma alvo e artefatos técnicos da coleta para apoiar a preparação "
            "inicial de Produção Antecipada de Provas (PAP). Não substitui advogado, "
            "petição judicial ou parecer pericial conclusivo."
        ),
    },
    "notarial": {
        "titulo": "Selo notarial / Ata notarial",
        "preco": os.getenv("PROVASOCIAL_PRECO_NOTARIAL", "sob consulta"),
        "descricao": (
            "Encaminhamento para reforço probatório por ata notarial ou validação equivalente, "
            "quando aplicável."
        ),
    },
    "pericial": {
        "titulo": "Consultoria Técnica Jurídica Individual",
        "preco": os.getenv("PROVASOCIAL_PRECO_PERICIAL", "sob consulta"),
        "descricao": (
            "Atendimento individual com análise humana do caso, priorização de elementos "
            "úteis à identificação judicial, estratégia técnica e encaminhamentos para "
            "advogado, PAP, quebra de sigilo ou reforço pericial."
        ),
    },
}
