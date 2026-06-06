"""Consulta a endpoints oEmbed públicos para metadados confiáveis.

oEmbed é um padrão aberto que retorna metadados estruturados de um conteúdo a
partir da sua URL, sem necessidade de token. Útil para complementar a captura
HTML (que pode ser bloqueada) com dados oficiais da plataforma.

YouTube e TikTok oferecem oEmbed público. Instagram e Facebook passaram a exigir
token de app, portanto não são consultados aqui.
"""

from __future__ import annotations

import requests

from backend.config import TIMEOUT, USER_AGENT, VERIFICAR_SSL

_ENDPOINTS = {
    "youtube": "https://www.youtube.com/oembed",
    "tiktok": "https://www.tiktok.com/oembed",
}


def consultar(plataforma: str, url: str) -> dict | None:
    """Retorna o dict oEmbed da plataforma, ou None se indisponível."""
    endpoint = _ENDPOINTS.get(plataforma)
    if not endpoint:
        return None
    try:
        resp = requests.get(
            endpoint,
            params={"url": url, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            verify=VERIFICAR_SSL,
        )
        if resp.status_code == 200:
            return resp.json()
    except (requests.RequestException, ValueError):
        pass
    return None
