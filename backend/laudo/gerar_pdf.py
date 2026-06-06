"""Gera o laudo de coleta em HTML e, quando possível, converte para PDF.

O laudo é auto-explicativo e auditável: lista todos os metadados, todos os
hashes SHA256, a cadeia de custódia e um QR code para o portal de verificação.
"""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from backend.config import PORTAL_VERIFICACAO, RAIZ
from backend.captura.render_capture import render_html_para_pdf


def _qr_base64(texto: str) -> str | None:
    """Gera um QR code PNG em base64 (data URI). Retorna None se lib ausente."""
    try:
        import qrcode
    except ImportError:
        return None
    img = qrcode.make(texto)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _logo_base64() -> str | None:
    """Carrega o logo do projeto como data URI para o laudo offline."""
    caminho = RAIZ / "static" / "if.png"
    if not caminho.exists():
        return None
    try:
        return base64.b64encode(caminho.read_bytes()).decode("ascii")
    except OSError:
        return None


def _linha(rotulo: str, valor) -> str:
    if valor in (None, "", [], {}):
        return ""
    return f"<tr><th>{html.escape(str(rotulo))}</th><td>{html.escape(str(valor))}</td></tr>"


def _carregar_comentarios(pasta: Path) -> dict | None:
    arquivo = pasta / "comentarios.json"
    if not arquivo.exists():
        return None
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def gerar(manifesto: dict, cadeia: dict, pasta: Path) -> dict:
    """Cria laudo.html e tenta gerar laudo.pdf. Retorna nomes de arquivo gerados."""
    codigo = manifesto.get("codigo_verificacao", "")
    url_verificacao = f"{PORTAL_VERIFICACAO}/{codigo}"
    qr = _qr_base64(url_verificacao)
    qr_html = (
        f'<img class="qr" src="data:image/png;base64,{qr}" alt="QR verificação"/>'
        if qr
        else f'<p class="muted">Verifique em: {html.escape(url_verificacao)}</p>'
    )
    logo = _logo_base64()
    logo_html = (
        f'<img class="logo-laudo" src="data:image/png;base64,{logo}" alt="CyberMarmouts"/>'
        if logo
        else '<div class="logo-fallback">CyberMarmouts</div>'
    )

    meta = manifesto.get("metadados", {})
    gerado = manifesto.get("gerado_em", {})

    # Tabela de metadados
    linhas_meta = "".join(
        _linha(k, v)
        for k, v in meta.items()
        if k not in ("open_graph", "json_ld") and not isinstance(v, (dict, list))
    )

    # Seção de análise de mídia (EXIF/GPS)
    midias = meta.get("midias_analisadas", [])
    linhas_midia = ""
    for i, m in enumerate(midias, start=1):
        gps = m.get("gps")
        gps_txt = (
            f"<span class='hash'>lat {gps['latitude']}, lon {gps['longitude']}</span>"
            if gps
            else "<span class='muted'>sem GPS</span>"
        )
        linhas_midia += (
            f"<tr><td>{i}</td><td class='mono'>{html.escape(m.get('arquivo',''))}</td>"
            f"<td>{html.escape(str(m.get('mime') or '—'))}</td>"
            f"<td>{html.escape(m.get('fonte','—'))}</td><td>{gps_txt}</td></tr>"
        )
    secao_midia = (
        f"""<h2>3. Análise de Mídia (EXIF/GPS)</h2>
<table class="lista">
  <tr><th>#</th><th>Arquivo</th><th>Tipo</th><th>Fonte</th><th>Geolocalização</th></tr>
  {linhas_midia}
</table>"""
        if midias
        else ""
    )

    # Seção de comentários coletados (amostra no laudo; arquivo completo nos artefatos).
    comentarios_info = _carregar_comentarios(pasta)
    secao_comentarios = ""
    if comentarios_info:
        comentarios = comentarios_info.get("comentarios", [])
        alvo = comentarios_info.get("alvo") or {}
        linhas_alvo = ""
        if alvo:
            linhas_alvo = (
                _linha("Comentário alvo buscado", alvo.get("trecho_busca"))
                + _linha("Comentário alvo encontrado", "sim" if alvo.get("encontrado") else "não")
                + _linha("Método alvo", alvo.get("metodo"))
                + _linha("Scrolls da busca alvo", alvo.get("scrolls_executados"))
                + _linha("OCR do alvo", alvo.get("ocr_status"))
                + _linha("Artefatos do alvo", ", ".join(alvo.get("artefatos", [])))
                + _linha("Observação do alvo", alvo.get("observacao"))
            )
        linhas_coment = "".join(
            f"<tr><td>{c.get('indice')}</td>"
            f"<td>{html.escape(str(c.get('autor_username') or c.get('autor_nome') or '—'))}</td>"
            f"<td>{html.escape(str(c.get('data_hora') or '—'))}</td>"
            f"<td>{html.escape(str(c.get('texto') or ''))}</td></tr>"
            for c in comentarios[:20]
        )
        secao_comentarios = f"""<h2>4. Comentários Coletados</h2>
<table>
  {_linha("Status", comentarios_info.get("status"))}
  {_linha("Quantidade", comentarios_info.get("quantidade"))}
  {_linha("Método", comentarios_info.get("metodo"))}
  {_linha("Observação", comentarios_info.get("observacao"))}
  {linhas_alvo}
</table>
<table class="lista">
  <tr><th>#</th><th>Autor</th><th>Data/Hora</th><th>Comentário</th></tr>
  {linhas_coment or '<tr><td colspan="4" class="muted">Nenhum comentário disponível para exibição no laudo.</td></tr>'}
</table>
<p class="muted">A lista completa, quando existente, consta em <span class="mono">comentarios.json</span> e <span class="mono">comentarios.txt</span>.</p>"""

    # Tabela de artefatos + hashes
    linhas_art = "".join(
        f"<tr><td>{html.escape(a['nome'])}</td><td>{html.escape(a['tipo'])}</td>"
        f"<td class='mono'>{html.escape(a['arquivo'])}</td>"
        f"<td class='mono hash'>{html.escape(a['sha256'])}</td></tr>"
        for a in manifesto.get("artefatos", [])
    )

    # Tabela da cadeia de custódia
    linhas_cadeia = "".join(
        f"<tr><td>{e['indice']}</td><td>{html.escape(e['etapa'])}</td>"
        f"<td>{html.escape(e['ator'])}</td><td>{html.escape(e['momento_brasilia'])}</td>"
        f"<td class='mono hash'>{html.escape(e['hash_atual'])}</td></tr>"
        for e in cadeia.get("etapas", [])
    )

    documento = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<title>Laudo de Coleta — {html.escape(manifesto.get('coleta_id',''))}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; margin: 40px; font-size: 12px; }}
  header {{ border-bottom: 3px solid #0f3460; padding-bottom: 12px; margin-bottom: 20px; }}
  h1 {{ font-size: 20px; margin: 0; color: #0f3460; }}
  h2 {{ font-size: 14px; color: #0f3460; border-left: 4px solid #e94560; padding-left: 8px; margin-top: 24px; }}
  .sub {{ color: #555; font-size: 11px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border: 1px solid #ddd; vertical-align: top; }}
  th {{ background: #f0f3f8; width: 200px; }}
  table.lista th {{ width: auto; }}
  .mono {{ font-family: 'Consolas', monospace; font-size: 10px; word-break: break-all; }}
  .hash {{ color: #0a6; }}
  .qr {{ width: 130px; height: 130px; }}
  .brand {{ display: flex; gap: 12px; align-items: center; }}
  .logo-laudo {{ width: 54px; height: 54px; object-fit: contain; }}
  .logo-fallback {{ font-weight: 700; color: #0f3460; }}
  .muted {{ color: #888; }}
  .box {{ background: #f9fafc; border: 1px solid #e0e6ef; padding: 12px; border-radius: 6px; }}
  .aviso {{ background: #fff8e1; border: 1px solid #ffe082; padding: 10px; border-radius: 6px; font-size: 11px; }}
  footer {{ margin-top: 30px; border-top: 1px solid #ccc; padding-top: 10px; color: #888; font-size: 10px; }}
  .topo {{ display: flex; justify-content: space-between; align-items: flex-start; }}
</style>
</head>
<body>
<header>
  <div class="topo">
    <div class="brand">
      {logo_html}
      <div>
        <h1>Laudo de Coleta de Evidência Digital</h1>
        <p class="sub">ProvaSocial — Extract · CyberMarmouts Inteligência Forense</p>
      </div>
    </div>
    <div style="text-align:center">
      {qr_html}
      <div class="mono" style="font-size:9px">{html.escape(codigo)}</div>
    </div>
  </div>
</header>

<h2>1. Identificação da Coleta</h2>
<table>
  {_linha("ID da coleta", manifesto.get("coleta_id"))}
  {_linha("Código de verificação", codigo)}
  {_linha("Caso", manifesto.get("caso"))}
  {_linha("URL alvo", manifesto.get("url_alvo"))}
  {_linha("Plataforma", manifesto.get("plataforma"))}
  {_linha("Analista responsável", manifesto.get("analista"))}
  {_linha("Coletado em (UTC)", gerado.get("utc"))}
  {_linha("Coletado em (Brasília)", gerado.get("brasilia"))}
  {_linha("Algoritmo de hash", manifesto.get("algoritmo_hash"))}
</table>

<h2>2. Metadados Extraídos</h2>
<table>{linhas_meta or '<tr><td class="muted">Nenhum metadado estruturado extraído.</td></tr>'}</table>

{secao_midia}

{secao_comentarios}

<h2>5. Artefatos Coletados e Hashes</h2>
<table class="lista">
  <tr><th>Nome</th><th>Tipo</th><th>Arquivo</th><th>SHA-256</th></tr>
  {linhas_art}
</table>
<div class="box mono" style="margin-top:8px">
  <strong>Hash final do manifesto:</strong><br/>{html.escape(manifesto.get("hash_manifesto",""))}
</div>

<h2>6. Cadeia de Custódia (CPP art. 158-A)</h2>
<table class="lista">
  <tr><th>#</th><th>Etapa</th><th>Ator</th><th>Momento (Brasília)</th><th>Hash do elo</th></tr>
  {linhas_cadeia}
</table>

<h2>7. Como Verificar a Integridade</h2>
<div class="aviso">
  Este laudo é auditável. Qualquer parte pode confirmar que os artefatos não foram
  alterados acessando <strong>{html.escape(PORTAL_VERIFICACAO)}/{html.escape(codigo)}</strong>
  ou executando o verificador local sobre a pasta da coleta. Se um único byte de
  qualquer artefato for modificado, a verificação acusará adulteração.
</div>

<footer>
  Documento gerado automaticamente por ProvaSocial-Extract v{html.escape(manifesto.get("versao",""))}.
  A coleta foi realizada de forma independente pelo servidor. Este documento constitui
  prova auditável para fins de Produção Antecipada de Provas (PAP) e pedido de quebra
  de sigilo. Não realiza, por si só, a identificação civil do titular do perfil, que
  depende de ordem judicial (Marco Civil da Internet, arts. 22 e 23).
</footer>
</body>
</html>"""

    caminho_html = pasta / "laudo.html"
    caminho_html.write_text(documento, encoding="utf-8")

    gerados = {"html": "laudo.html"}
    caminho_pdf = pasta / "laudo.pdf"
    if render_html_para_pdf(caminho_html, caminho_pdf):
        gerados["pdf"] = "laudo.pdf"
    return gerados
