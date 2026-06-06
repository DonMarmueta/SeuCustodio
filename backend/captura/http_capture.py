"""Captura HTTP de baixo nível: HTML cru, headers e status.

Esta é a primeira camada de evidência — registra exatamente o que o servidor
retornou, incluindo os cabeçalhos HTTP, que ajudam a datar e contextualizar a
coleta.
"""

from __future__ import annotations

import requests

from backend.config import TIMEOUT, USER_AGENT, VERIFICAR_SSL


def capturar_http(url: str) -> dict:
    """Faz GET na URL e devolve conteúdo + metadados da resposta.

    Retorna dict com: ok, status, html (texto), headers, url_final, erro.
    """
    resultado: dict = {
        "ok": False,
        "status": None,
        "html": "",
        "headers": {},
        "url_final": url,
        "erro": None,
    }
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=TIMEOUT,
            allow_redirects=True,
            verify=VERIFICAR_SSL,
        )
        resultado["status"] = resp.status_code
        resultado["html"] = resp.text
        resultado["headers"] = dict(resp.headers)
        resultado["url_final"] = resp.url
        resultado["ok"] = resp.status_code == 200
        if resp.status_code == 404:
            resultado["erro"] = "PERFIL/POST NÃO ENCONTRADO OU DELETADO (404)"
        elif resp.status_code == 403:
            resultado["erro"] = "ACESSO BLOQUEADO (403)"
    except requests.RequestException as exc:
        resultado["erro"] = f"ERRO DE REDE: {exc}"
    return resultado


def baixar_binario(url: str) -> tuple[bytes | None, str | None]:
    """Baixa um recurso binário (imagem/vídeo). Retorna (dados, content_type)."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            stream=True,
            verify=VERIFICAR_SSL,
        )
        if resp.status_code == 200:
            return resp.content, resp.headers.get("Content-Type")
    except requests.RequestException:
        pass
    return None, None
