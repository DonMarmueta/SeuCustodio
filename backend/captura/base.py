"""Identificação de plataforma e normalização de URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Mapeia domínios conhecidos para um identificador de plataforma.
_DOMINIOS = {
    "x": ("x.com", "twitter.com", "mobile.twitter.com"),
    "instagram": ("instagram.com", "www.instagram.com"),
    "facebook": ("facebook.com", "www.facebook.com", "fb.com", "m.facebook.com"),
    "tiktok": ("tiktok.com", "www.tiktok.com", "vm.tiktok.com"),
    "youtube": ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"),
}


def identificar_plataforma(url: str) -> str:
    """Retorna o identificador da plataforma a partir da URL ('generico' se desconhecida)."""
    host = (urlparse(url).hostname or "").lower()
    for plataforma, dominios in _DOMINIOS.items():
        if host in dominios:
            return plataforma
    return "generico"


def slug_seguro(texto: str, tamanho: int = 40) -> str:
    """Gera um trecho seguro para nome de arquivo/pasta."""
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "_", texto).strip("_")
    return limpo[:tamanho] or "alvo"
