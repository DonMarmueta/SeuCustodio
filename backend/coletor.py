"""Orquestrador CLI da coleta forense.

Fluxo:
  1. Identifica a plataforma e prepara a pasta WORM da evidência.
  2. Captura HTTP (HTML cru, headers, status).
  3. Captura render (screenshot full-page + PDF + DOM renderizado).
  4. Baixa a mídia principal (og:image), quando disponível.
  5. Extrai metadados específicos da plataforma.
  6. Calcula hashes de todos os artefatos.
  7. Registra a cadeia de custódia (CPP 158-A).
  8. Constrói o manifesto encadeado.
  9. Gera o laudo (HTML + PDF).

Uso:
  python -m backend.coletor --url "https://x.com/user/status/123" \
      --analista "CyberMarmouts" --caso "Caso02" --evidencia "EV-001"
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

from backend.banner import imprimir_banner
from backend.config import ANALISTA_PADRAO, PASTA_EVIDENCIAS
from backend.captura import base, exif, http_capture, metadados, oembed, render_capture
from backend.captura.comentarios import comentarios_para_txt

# Limite de mídias baixadas por coleta (controla custo/tempo).
MAX_MIDIAS = 6
from backend.custodia import hashing, manifesto as mod_manifesto
from backend.custodia.cadeia import CadeiaCustodia
from backend.custodia.timestamp import agora
from backend.laudo import gerar_pdf


def _gerar_codigo() -> str:
    """Código público de verificação (curto, sem ambiguidade)."""
    return secrets.token_hex(6).upper()


def _extensao(content_type: str | None, url: str) -> str:
    """Decide a extensão do arquivo de mídia a partir do content-type ou da URL."""
    mapa = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }
    if content_type:
        for chave, ext in mapa.items():
            if chave in content_type:
                return ext
    # Fallback: extensão presente na URL
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm"):
        if ext in url.lower():
            return ".jpg" if ext == ".jpeg" else ext
    return ".bin"


def _registrar_artefato(pasta: Path, nome: str, tipo: str, arquivo: str) -> dict:
    caminho = pasta / arquivo
    return {
        "nome": nome,
        "tipo": tipo,
        "arquivo": arquivo,
        "sha256": hashing.hash_arquivo(caminho),
        "tamanho": caminho.stat().st_size,
    }


def coletar(
    url: str,
    analista: str,
    caso: str | None,
    evidencia: str | None,
    comentario_alvo: str | None = None,
    modo_pericial: bool = False,
) -> dict:
    plataforma = base.identificar_plataforma(url)
    codigo = _gerar_codigo()
    coleta_id = evidencia or f"PS-{agora()['utc'][:10]}-{codigo[:4]}"

    nome_pasta = f"{base.slug_seguro(coleta_id)}_{codigo}"
    pasta = PASTA_EVIDENCIAS / nome_pasta
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "midia").mkdir(exist_ok=True)

    print(f"[*] Coleta {coleta_id} | plataforma={plataforma}")
    print(f"[*] Pasta: {pasta}")

    cadeia = CadeiaCustodia(coleta_id=coleta_id, url_alvo=url, plataforma=plataforma)
    cadeia.registrar("reconhecimento", analista, f"URL alvo identificada: {url}")
    if comentario_alvo:
        cadeia.registrar(
            "reconhecimento",
            analista,
            f"Comentário alvo informado para busca direcionada: {comentario_alvo[:120]}",
        )
    cadeia.registrar("isolamento", "worker@servidor", f"Coleta isolada na pasta {nome_pasta}")

    artefatos: list[dict] = []

    # 2) Captura HTTP
    print("[*] Captura HTTP...")
    http = http_capture.capturar_http(url)
    (pasta / "raw.html").write_text(http["html"], encoding="utf-8")
    (pasta / "resposta_http.json").write_text(
        json.dumps(
            {
                "status": http["status"],
                "url_final": http["url_final"],
                "headers": http["headers"],
                "erro": http["erro"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    artefatos.append(_registrar_artefato(pasta, "HTML cru", "html", "raw.html"))
    artefatos.append(_registrar_artefato(pasta, "Resposta HTTP", "metadados", "resposta_http.json"))
    cadeia.registrar("coleta", "worker@servidor", f"HTTP GET status={http['status']}", artefatos[-2]["sha256"])

    # 3) Captura render (Playwright)
    print("[*] Captura render (Playwright)...")
    render = render_capture.capturar_render(
        url,
        pasta,
        comentario_alvo=comentario_alvo,
        modo_pericial=modo_pericial,
    )
    html_para_metadados = http["html"]
    if render["ok"]:
        if render.get("captura_autenticada"):
            print("    [+] Captura autenticada com sessão do operador")
        if render.get("modo_pericial"):
            print("    [+] Modo pericial/premium: gravação de tela habilitada")
        if render.get("html_render"):
            (pasta / "render.html").write_text(render["html_render"], encoding="utf-8")
            artefatos.append(_registrar_artefato(pasta, "DOM renderizado", "html", "render.html"))
            html_para_metadados = render["html_render"]
        for tipo_arq, nome_arq in render["arquivos"].items():
            artefatos.append(_registrar_artefato(pasta, tipo_arq, tipo_arq, nome_arq))
        cadeia.registrar("fixacao", "worker@servidor", "Render visual (screenshot/PDF) fixado", artefatos[-1]["sha256"])

        comentarios_resultado = render.get("comentarios")
        if comentarios_resultado:
            (pasta / "comentarios.json").write_text(
                json.dumps(comentarios_resultado, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (pasta / "comentarios.txt").write_text(
                comentarios_para_txt(comentarios_resultado),
                encoding="utf-8",
            )
            artefato_comentarios_json = _registrar_artefato(
                pasta, "Comentários (JSON)", "comentarios", "comentarios.json"
            )
            artefatos.append(artefato_comentarios_json)
            artefatos.append(_registrar_artefato(pasta, "Comentários (TXT)", "comentarios", "comentarios.txt"))
            alvo = comentarios_resultado.get("alvo") or {}
            if alvo:
                (pasta / "comentario_alvo.json").write_text(
                    json.dumps(alvo, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                artefatos.append(
                    _registrar_artefato(pasta, "Comentário alvo (JSON)", "comentarios", "comentario_alvo.json")
                )
                for arquivo_alvo in alvo.get("artefatos", []):
                    caminho_alvo = pasta / arquivo_alvo
                    if caminho_alvo.exists():
                        artefatos.append(
                            _registrar_artefato(
                                pasta,
                                f"Comentário alvo - {arquivo_alvo}",
                                "comentario_alvo",
                                arquivo_alvo,
                            )
                        )
            cadeia.registrar(
                "coleta",
                "worker@servidor",
                f"Comentários visíveis coletados: {comentarios_resultado.get('quantidade', 0)}",
                artefato_comentarios_json["sha256"],
            )
    else:
        print(f"    [!] Render indisponível: {render['erro']}")

    # 4) Extrair metadados
    print("[*] Extraindo metadados...")
    meta = metadados.extrair(plataforma, url, html_para_metadados)
    meta["captura_http_status"] = http["status"]
    meta["captura_erro"] = http["erro"]
    meta["captura_autenticada"] = "sim" if render.get("captura_autenticada") else "nao"
    meta["modo_pericial"] = "sim" if modo_pericial else "nao"
    if comentario_alvo:
        meta["comentario_alvo_trecho"] = comentario_alvo
    if render.get("captura_autenticada"):
        meta["sessao_operador_arquivo"] = render.get("storage_state_arquivo")
        meta["sessao_operador_hash"] = render.get("storage_state_hash")
        meta["nota_sessao_operador"] = (
            "Captura realizada com sessão autenticada do operador. O arquivo de sessão "
            "contém cookies/tokens e não é anexado ao laudo; registra-se apenas seu hash "
            "para rastreabilidade interna."
        )
    if render.get("comentarios"):
        comentarios_resultado = render["comentarios"]
        meta["comentarios_status"] = comentarios_resultado.get("status")
        meta["comentarios_quantidade"] = comentarios_resultado.get("quantidade", 0)
        meta["comentarios_observacao"] = comentarios_resultado.get("observacao")
        alvo = comentarios_resultado.get("alvo") or {}
        if alvo:
            meta["comentario_alvo_encontrado"] = "sim" if alvo.get("encontrado") else "nao"
            meta["comentario_alvo_ocr_status"] = alvo.get("ocr_status")
            meta["comentario_alvo_artefatos"] = ", ".join(alvo.get("artefatos", []))
        if comentarios_resultado.get("status") in ("bloqueado_por_login", "erro", "nao_encontrado"):
            meta["comentarios_requer_assessoria"] = True

    # 4b) oEmbed (metadados oficiais da plataforma, quando público)
    dados_oembed = oembed.consultar(plataforma, url)
    if dados_oembed:
        meta["oembed"] = dados_oembed
        print(f"    [+] oEmbed obtido ({plataforma})")

    # 5) Baixar TODAS as mídias candidatas e analisar EXIF/GPS de cada uma
    candidatas = metadados.midias_candidatas(meta)[:MAX_MIDIAS]
    analises_midia: list[dict] = []
    for idx, midia_url in enumerate(candidatas, start=1):
        print(f"[*] Baixando mídia {idx}/{len(candidatas)}: {midia_url[:70]}")
        dados, ctype = http_capture.baixar_binario(midia_url)
        if not dados:
            continue
        ext = _extensao(ctype, midia_url)
        rel = f"midia/midia_{idx}{ext}"
        (pasta / rel).write_bytes(dados)
        artefatos.append(_registrar_artefato(pasta, f"Mídia {idx}", "midia", rel))
        cadeia.registrar("coleta", "worker@servidor", f"Mídia {idx} baixada de {midia_url}", artefatos[-1]["sha256"])

        # Análise forense da mídia (ExifTool ou Pillow)
        analise = exif.analisar_midia(pasta / rel)
        analise["url_origem"] = midia_url
        analises_midia.append(analise)
        if analise.get("gps"):
            print(f"    [!] GPS encontrado na mídia {idx}: {analise['gps']}")

    if analises_midia:
        meta["midias_analisadas"] = analises_midia
        meta["exif_fonte"] = "exiftool" if exif.exiftool_disponivel() else "pillow"

    (pasta / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    artefatos.append(_registrar_artefato(pasta, "Metadados", "metadados", "metadados.json"))

    # 6/7) Encadeamento e armazenamento na cadeia
    cadeia.registrar("processamento", "worker@servidor", "Metadados extraídos e hasheados", artefatos[-1]["sha256"])
    cadeia.registrar("acondicionamento", "worker@servidor", f"{len(artefatos)} artefatos acondicionados")
    cadeia.registrar("armazenamento", "worker@servidor", "Evidência armazenada (pasta WORM)")
    dados_cadeia = cadeia.para_dict()
    (pasta / "cadeia_custodia.json").write_text(
        json.dumps(dados_cadeia, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 8) Manifesto
    print("[*] Construindo manifesto...")
    manifesto = mod_manifesto.construir(
        coleta_id=coleta_id,
        codigo_verificacao=codigo,
        url_alvo=url,
        plataforma=plataforma,
        analista=analista,
        caso=caso,
        artefatos=artefatos,
        metadados=meta,
        cadeia=dados_cadeia,
    )
    mod_manifesto.salvar(manifesto, pasta / "manifesto.json")

    # 9) Laudo
    print("[*] Gerando laudo...")
    laudo = gerar_pdf.gerar(manifesto, dados_cadeia, pasta)

    print("\n========================================")
    print(f" Coleta concluída: {coleta_id}")
    print(f" Código de verificação: {codigo}")
    print(f" Artefatos: {len(artefatos)}")
    print(f" Hash do manifesto: {manifesto['hash_manifesto']}")
    print(f" Laudo: {', '.join(laudo.values())}")
    print(f" Pasta: {pasta}")
    print("========================================")

    return {"pasta": str(pasta), "codigo": codigo, "manifesto": manifesto, "laudo": laudo}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coletor forense de evidências de redes sociais.")
    parser.add_argument("--url", required=True, help="URL do post/perfil a coletar.")
    parser.add_argument("--analista", default=ANALISTA_PADRAO, help="Responsável pela coleta.")
    parser.add_argument("--caso", default=None, help="Identificação do caso (opcional).")
    parser.add_argument("--evidencia", default=None, help="ID da evidência (ex.: EV-001).")
    parser.add_argument(
        "--comentario-alvo",
        default=None,
        help="Trecho do comentário específico que deve ser buscado com scroll direcionado.",
    )
    parser.add_argument(
        "--modo-pericial",
        action="store_true",
        help="Habilita captura premium/pericial com gravação de vídeo da navegação Playwright.",
    )
    args = parser.parse_args(argv)

    try:
        imprimir_banner()
        coletar(
            args.url,
            args.analista,
            args.caso,
            args.evidencia,
            comentario_alvo=args.comentario_alvo,
            modo_pericial=args.modo_pericial,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
