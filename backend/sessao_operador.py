"""Cria/renova uma sessão autenticada do operador para capturas Playwright.

Uso:
    python -m backend.sessao_operador --plataforma instagram
    python -m backend.sessao_operador --url https://www.facebook.com/

O comando abre um Chromium VISÍVEL. Faça login manualmente, resolva 2FA/captcha
se necessário e pressione ENTER no terminal. O estado autenticado será salvo em
`sessoes/operador.json` (ou no caminho definido por PROVASOCIAL_STORAGE_STATE).

ATENÇÃO: o arquivo gerado contém cookies/tokens. Ele é segredo operacional.
Não versionar, não anexar ao laudo e não compartilhar.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.banner import imprimir_banner
from backend.config import BROWSER_EXECUTABLE_PATH, STORAGE_STATE_OPERADOR, USER_AGENT
from backend.custodia.hashing import hash_arquivo

URLS_PLATAFORMA = {
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "x": "https://x.com/",
    "tiktok": "https://www.tiktok.com/",
    "youtube": "https://www.youtube.com/",
}


def criar_sessao(url: str, saida: Path = STORAGE_STATE_OPERADOR) -> Path:
    """Abre navegador visível, aguarda login manual e salva storage_state."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Playwright não instalado. Rode: pip install playwright && playwright install chromium"
        ) from exc

    saida.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        launch_args = {"headless": False}
        if BROWSER_EXECUTABLE_PATH:
            launch_args["executable_path"] = BROWSER_EXECUTABLE_PATH
        navegador = p.chromium.launch(**launch_args)
        contexto = navegador.new_context(
            user_agent=USER_AGENT,
            locale="pt-BR",
            viewport={"width": 1366, "height": 900},
        )
        pagina = contexto.new_page()
        pagina.goto(url, wait_until="domcontentloaded", timeout=60_000)

        print("\nFaça login na janela do navegador que abriu.")
        print("Depois de confirmar que a conta está logada, volte aqui e pressione ENTER.")
        input("Pressione ENTER para salvar a sessão autenticada...")

        contexto.storage_state(path=str(saida))
        navegador.close()

    return saida


def main() -> int:
    parser = argparse.ArgumentParser(description="Gerar sessão autenticada do operador.")
    parser.add_argument(
        "--plataforma",
        choices=sorted(URLS_PLATAFORMA),
        default="instagram",
        help="Plataforma onde fazer login (padrão: instagram).",
    )
    parser.add_argument("--url", default=None, help="URL customizada de login.")
    parser.add_argument("--saida", default=str(STORAGE_STATE_OPERADOR), help="Arquivo de saída.")
    args = parser.parse_args()

    imprimir_banner()
    url = args.url or URLS_PLATAFORMA[args.plataforma]
    saida = criar_sessao(url, Path(args.saida))

    print("\nSessão salva com sucesso.")
    print(f"Arquivo : {saida}")
    print(f"SHA-256 : {hash_arquivo(saida)}")
    print("\nGuarde esse arquivo como segredo operacional (cookies/tokens).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
