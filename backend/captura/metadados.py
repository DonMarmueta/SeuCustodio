"""Extração de metadados por plataforma.

Trabalha sobre o HTML capturado (preferencialmente o DOM renderizado pelo
Playwright). Cada plataforma tem heurísticas próprias; quando não há extrator
específico, recai no genérico (OpenGraph + JSON-LD + meta tags).
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from backend.custodia.timestamp import converter_unix

try:
    from bs4 import BeautifulSoup
except ImportError:  # degradação controlada
    BeautifulSoup = None  # type: ignore


def extrair(plataforma: str, url: str, html: str) -> dict:
    """Roteia para o extrator da plataforma e sempre agrega o genérico."""
    base = _extrair_generico(url, html)
    especifico = {
        "x": _extrair_x,
        "instagram": _extrair_instagram,
        "facebook": _extrair_facebook,
        "tiktok": _extrair_tiktok,
        "youtube": _extrair_youtube,
    }.get(plataforma)

    if especifico:
        base.update({k: v for k, v in especifico(url, html).items() if v})
    base["plataforma"] = plataforma
    base["url_alvo"] = url
    enriquecer_timestamps(base)
    return base


def enriquecer_timestamps(meta: dict) -> None:
    """Converte campos *_epoch (Unix em segundos) para UTC + Brasília legíveis."""
    for chave in list(meta.keys()):
        if chave.endswith("_epoch") and isinstance(meta[chave], (int, float)):
            try:
                conv = converter_unix(meta[chave], unidade="s")
                meta[chave.replace("_epoch", "_datahora")] = {
                    "utc": conv["utc"],
                    "brasilia": conv["brasilia"],
                }
            except (ValueError, OverflowError, OSError):
                continue


def midias_candidatas(meta: dict) -> list[str]:
    """Reúne URLs de mídia (imagem/vídeo) encontradas nos metadados, sem duplicar."""
    urls: list[str] = []

    def _add(valor):
        if isinstance(valor, str) and valor.startswith("http") and valor not in urls:
            urls.append(valor)

    og = meta.get("open_graph", {})
    for chave in ("og:image", "og:image:secure_url", "og:video", "og:video:url", "og:video:secure_url"):
        _add(og.get(chave))

    tw = meta.get("twitter_card", {})
    for chave in ("twitter:image", "twitter:player:stream"):
        _add(tw.get(chave))

    _add(meta.get("imagem"))

    # Imagens declaradas em JSON-LD
    for bloco in meta.get("json_ld", []):
        if isinstance(bloco, dict):
            img = bloco.get("image") or bloco.get("thumbnailUrl")
            if isinstance(img, str):
                _add(img)
            elif isinstance(img, list):
                for i in img:
                    _add(i if isinstance(i, str) else i.get("url") if isinstance(i, dict) else None)
            elif isinstance(img, dict):
                _add(img.get("url"))

    return urls


# --------------------------------------------------------------------------- #
# Genérico — OpenGraph / JSON-LD / meta tags                                   #
# --------------------------------------------------------------------------- #
def _extrair_generico(url: str, html: str) -> dict:
    dados: dict = {
        "titulo": None,
        "descricao": None,
        "autor": None,
        "imagem": None,
        "open_graph": {},
        "twitter_card": {},
        "json_ld": [],
    }
    if not BeautifulSoup:
        m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if m:
            dados["titulo"] = m.group(1).strip()
        return dados

    soup = BeautifulSoup(html, "html.parser")

    if soup.title and soup.title.string:
        dados["titulo"] = soup.title.string.strip()

    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name") or ""
        conteudo = tag.get("content")
        if not conteudo:
            continue
        prop = prop.lower()
        if prop.startswith("og:"):
            dados["open_graph"][prop] = conteudo
        if prop.startswith("twitter:"):
            dados["twitter_card"][prop] = conteudo
        if prop in ("description", "og:description") and not dados["descricao"]:
            dados["descricao"] = conteudo
        if prop in ("author", "article:author") and not dados["autor"]:
            dados["autor"] = conteudo
        if prop == "og:image" and not dados["imagem"]:
            dados["imagem"] = conteudo

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            dados["json_ld"].append(json.loads(script.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue

    return dados


# --------------------------------------------------------------------------- #
# X / Twitter                                                                  #
# --------------------------------------------------------------------------- #
def _extrair_x(url: str, html: str) -> dict:
    dados: dict = {
        "username": _username_da_url(url),
        "user_id": None,
        "status_id": None,
        "display_name": None,
        "data_post": None,
        "conta_status": "ATIVO",
    }

    # status_id (post) presente na própria URL
    m = re.search(r"/status/(\d+)", url)
    if m:
        dados["status_id"] = m.group(1)

    # user_id numérico imutável — sobrevive a troca de @
    for padrao in (r'"user_id_str"\s*:\s*"(\d+)"', r'"userId"\s*:\s*"(\d+)"', r'"id_str"\s*:\s*"(\d+)"', r'data-user-id="(\d+)"'):
        m = re.search(padrao, html)
        if m:
            dados["user_id"] = m.group(1)
            break

    m = re.search(r'"created_at"\s*:\s*"([^"]+)"', html)
    if m:
        dados["data_post"] = m.group(1)

    # display name a partir do <title>: "Nome (@user) / X"
    m = re.search(r"<title>([^<]+?)\s*\(@", html, re.IGNORECASE)
    if m:
        dados["display_name"] = m.group(1).strip()

    if re.search(r"Account suspended|conta suspensa", html, re.IGNORECASE):
        dados["conta_status"] = "CONTA SUSPENSA"
    elif "This account doesn’t exist" in html or "Esta conta não existe" in html:
        dados["conta_status"] = "CONTA INEXISTENTE/DELETADA"

    return dados


# --------------------------------------------------------------------------- #
# Instagram                                                                    #
# --------------------------------------------------------------------------- #
def _extrair_instagram(url: str, html: str) -> dict:
    dados: dict = {"username": _username_da_url(url), "user_id": None, "shortcode": None, "data_post": None}
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if m:
        dados["shortcode"] = m.group(1)
    m = re.search(r'"owner"\s*:\s*\{[^}]*"id"\s*:\s*"(\d+)"', html)
    if m:
        dados["user_id"] = m.group(1)
    m = re.search(r'"taken_at_timestamp"\s*:\s*(\d+)', html)
    if m:
        dados["data_post_epoch"] = int(m.group(1))
    _marcar_identificacao(
        dados,
        "Instagram",
        disponivel=bool(dados["user_id"]),
    )
    return dados


# --------------------------------------------------------------------------- #
# Facebook                                                                     #
# --------------------------------------------------------------------------- #
def _extrair_facebook(url: str, html: str) -> dict:
    dados: dict = {"post_id": None, "page_id": None}
    m = re.search(r"/posts/(\d+)", url) or re.search(r"story_fbid=(\d+)", url)
    if m:
        dados["post_id"] = m.group(1)
    m = re.search(r'"pageID"\s*:\s*"(\d+)"', html) or re.search(r'"userID"\s*:\s*"(\d+)"', html)
    if m:
        dados["page_id"] = m.group(1)
    _marcar_identificacao(dados, "Facebook", disponivel=bool(dados["page_id"]))
    return dados


# --------------------------------------------------------------------------- #
# TikTok                                                                       #
# --------------------------------------------------------------------------- #
def _extrair_tiktok(url: str, html: str) -> dict:
    dados: dict = {"username": _username_da_url(url), "aweme_id": None, "author_id": None, "data_post_epoch": None}
    m = re.search(r"/video/(\d+)", url)
    if m:
        dados["aweme_id"] = m.group(1)
    m = re.search(r'"authorId"\s*:\s*"(\d+)"', html) or re.search(r'"id"\s*:\s*"(\d+)"\s*,\s*"uniqueId"', html)
    if m:
        dados["author_id"] = m.group(1)
    m = re.search(r'"createTime"\s*:\s*"?(\d{10})"?', html)
    if m:
        dados["data_post_epoch"] = int(m.group(1))
    return dados


# --------------------------------------------------------------------------- #
# YouTube                                                                      #
# --------------------------------------------------------------------------- #
def _extrair_youtube(url: str, html: str) -> dict:
    dados: dict = {"video_id": None, "channel_id": None, "data_publicacao": None}
    parsed = urlparse(url)
    if parsed.hostname and "youtu.be" in parsed.hostname:
        dados["video_id"] = parsed.path.lstrip("/")
    else:
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
        if m:
            dados["video_id"] = m.group(1)
    m = re.search(r'"channelId"\s*:\s*"([^"]+)"', html)
    if m:
        dados["channel_id"] = m.group(1)
    m = re.search(r'"publishDate"\s*:\s*"([^"]+)"', html) or re.search(r'itemprop="datePublished"\s+content="([^"]+)"', html)
    if m:
        dados["data_publicacao"] = m.group(1)
    return dados


# --------------------------------------------------------------------------- #
# Auxiliares                                                                   #
# --------------------------------------------------------------------------- #
def _marcar_identificacao(dados: dict, plataforma: str, disponivel: bool) -> None:
    """Registra de forma explícita se o identificador numérico foi obtido.

    Documentar a indisponibilidade FORTALECE a prova (mostra que a limitação foi
    reconhecida) e serve de gancho para a assessoria especializada, que conduz o
    pedido de quebra de sigilo à plataforma.
    """
    if disponivel:
        dados["id_numerico_status"] = "disponível"
        dados["identificacao_requer_assessoria"] = False
    else:
        dados["id_numerico_status"] = "indisponível por captura pública (perfil deslogado)"
        dados["nota_identificacao"] = (
            f"O identificador numérico interno do {plataforma} não é exposto a visitantes "
            "deslogados. A identificação civil do titular depende de ofício à plataforma "
            "(Marco Civil da Internet, art. 22). A captura preserva username, URL, conteúdo, "
            "data e hash — base suficiente para o pedido judicial. Para conduzir a quebra de "
            "sigilo e a identificação, há assessoria forense especializada."
        )
        dados["identificacao_requer_assessoria"] = True


def _username_da_url(url: str) -> str | None:
    """Extrai o primeiro segmento de path como username (heurística comum)."""
    caminho = urlparse(url).path.strip("/")
    if not caminho:
        return None
    primeiro = caminho.split("/")[0]
    primeiro = primeiro.lstrip("@")
    # Evita confundir prefixos de rota com usernames.
    if primeiro.lower() in ("p", "reel", "tv", "watch", "status", "video", "posts", "shorts"):
        return None
    return primeiro or None
