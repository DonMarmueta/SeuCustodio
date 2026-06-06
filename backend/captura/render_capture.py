"""Captura visual via navegador headless (Playwright).

Resolve o problema das páginas SPA (X, Instagram), onde o HTML inicial não
contém os dados — só após o JavaScript renderizar. Produz screenshot full-page,
PDF e o HTML já renderizado (DOM final).

Se o Playwright não estiver instalado, as funções retornam erro de forma
controlada, permitindo que o coletor degrade para captura HTTP simples.
"""

from __future__ import annotations

from pathlib import Path

from backend.captura.comentarios import extrair_comentarios_pagina
from backend.captura.base import identificar_plataforma
from backend.config import (
    BROWSER_EXECUTABLE_PATH,
    STORAGE_STATE_OPERADOR,
    TIMEOUT,
    USAR_SESSAO_OPERADOR,
    USER_AGENT,
)
from backend.custodia.hashing import hash_arquivo


def playwright_disponivel() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def capturar_render(
    url: str,
    pasta: Path,
    prefixo: str = "",
    comentario_alvo: str | None = None,
    modo_pericial: bool = False,
) -> dict:
    """Abre a URL em Chromium headless e salva screenshot + PDF + HTML renderizado.

    Retorna dict com caminhos relativos gerados e/ou erro.
    """
    resultado: dict = {
        "ok": False,
        "arquivos": {},
        "erro": None,
        "html_render": None,
        "captura_autenticada": False,
        "storage_state_hash": None,
        "storage_state_arquivo": None,
        "comentarios": None,
        "modo_pericial": modo_pericial,
    }

    if not playwright_disponivel():
        resultado["erro"] = (
            "Playwright não instalado. Rode: pip install playwright && playwright install chromium"
        )
        return resultado

    from playwright.sync_api import sync_playwright

    nome_png = f"{prefixo}screenshot.png"
    nome_pdf = f"{prefixo}pagina.pdf"

    try:
        with sync_playwright() as p:
            launch_args = {"headless": True}
            if BROWSER_EXECUTABLE_PATH:
                launch_args["executable_path"] = BROWSER_EXECUTABLE_PATH
            navegador = p.chromium.launch(**launch_args)
            contexto_args = {
                "user_agent": USER_AGENT,
                "locale": "pt-BR",
                "viewport": {"width": 1366, "height": 900},
            }
            video_dir = pasta / "video"
            if modo_pericial:
                video_dir.mkdir(exist_ok=True)
                contexto_args["record_video_dir"] = str(video_dir)
                contexto_args["record_video_size"] = {"width": 1366, "height": 900}
            if USAR_SESSAO_OPERADOR and STORAGE_STATE_OPERADOR.exists():
                contexto_args["storage_state"] = str(STORAGE_STATE_OPERADOR)
                resultado["captura_autenticada"] = True
                resultado["storage_state_hash"] = hash_arquivo(STORAGE_STATE_OPERADOR)
                resultado["storage_state_arquivo"] = STORAGE_STATE_OPERADOR.name

            contexto = navegador.new_context(**contexto_args)
            pagina = contexto.new_page()
            pagina.goto(url, wait_until="networkidle", timeout=TIMEOUT * 1000)
            # Pequena espera adicional para conteúdo lazy-load.
            pagina.wait_for_timeout(2500)

            plataforma = identificar_plataforma(url)
            resultado["comentarios"] = extrair_comentarios_pagina(
                pagina,
                plataforma,
                url,
                comentario_alvo=comentario_alvo,
                pasta=pasta,
            )

            resultado["html_render"] = pagina.content()

            pagina.screenshot(path=str(pasta / nome_png), full_page=True)
            resultado["arquivos"]["screenshot"] = nome_png

            # PDF só é suportado em Chromium headless.
            try:
                pagina.pdf(path=str(pasta / nome_pdf), print_background=True)
                resultado["arquivos"]["pdf"] = nome_pdf
            except Exception:  # pragma: no cover - depende do ambiente
                pass

            video = pagina.video
            contexto.close()
            if modo_pericial and video:
                try:
                    caminho_video = Path(video.path())
                    destino = video_dir / "captura_pericial.webm"
                    caminho_video.replace(destino)
                    resultado["arquivos"]["video_captura"] = "video/captura_pericial.webm"
                except Exception as exc:  # noqa: BLE001
                    resultado["erro_video"] = f"Falha ao salvar vídeo pericial: {exc}"
            navegador.close()
            resultado["ok"] = True
    except Exception as exc:  # noqa: BLE001
        resultado["erro"] = f"Falha no render: {exc}"

    return resultado


def render_html_para_pdf(caminho_html: Path, caminho_pdf: Path) -> bool:
    """Renderiza um arquivo HTML local em PDF (usado para o laudo)."""
    if not playwright_disponivel():
        return False
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            launch_args = {"headless": True}
            if BROWSER_EXECUTABLE_PATH:
                launch_args["executable_path"] = BROWSER_EXECUTABLE_PATH
            navegador = p.chromium.launch(**launch_args)
            pagina = navegador.new_page()
            pagina.goto(caminho_html.resolve().as_uri(), wait_until="networkidle")
            pagina.pdf(path=str(caminho_pdf), print_background=True, format="A4")
            navegador.close()
        return True
    except Exception:  # noqa: BLE001
        return False
