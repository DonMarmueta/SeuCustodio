"""Extração best-effort de comentários visíveis via Playwright.

Comentários são frequentemente carregados sob demanda e variam muito por
plataforma. Este módulo não promete "todos os comentários"; ele preserva os
comentários visíveis/acessíveis no momento da captura e documenta quando a
plataforma bloqueia a coleta por login/paginação.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

MAX_COMENTARIOS = 80
SCROLLS = 5
CLICKS_EXPANDIR = 4
SCROLLS_BUSCA_ALVO = 35

_LOGIN_RE = re.compile(
    r"(log in|login|sign up|entrar|iniciar sessão|crie uma conta|cadastre-se)",
    re.IGNORECASE,
)
_CURTIDAS_RE = re.compile(r"^\d+([.,]\d+)?\s*(curtidas?|likes?)$", re.IGNORECASE)
_TEMPO_RELATIVO_RE = re.compile(
    r"^(há\s+)?\d+\s*(s|seg|segundo?s?|min|minuto?s?|h|hora?s?|d|dia?s?|sem|semana?s?)$",
    re.IGNORECASE,
)
_RESPOSTAS_RE = re.compile(
    r"^(ver|view)\s+(todas?\s+)?(as\s+)?\d+\s+(respostas?|replies)$",
    re.IGNORECASE,
)
_FOOTER_RE = re.compile(
    r"^(privacidade|localizações|localizacoes|instagram lite|meta ai|meta verified|"
    r"português \(brasil\)|portugues \(brasil\)|©\s*\d{4}\s+instagram from meta)$",
    re.IGNORECASE,
)


def extrair_comentarios_pagina(
    pagina,
    plataforma: str,
    url: str,
    comentario_alvo: str | None = None,
    pasta: Path | None = None,
) -> dict:
    """Coleta comentários visíveis na página Playwright já carregada.

    Retorna um dict JSON-safe com status, método, quantidade e lista de
    comentários. Em caso de login wall, retorna status bloqueado.
    """
    try:
        alvo = _buscar_comentario_alvo(pagina, plataforma, comentario_alvo, pasta) if comentario_alvo else None

        _expandir_comentarios(pagina)
        _scrollar(pagina)
        comentarios = pagina.evaluate(_JS_EXTRATOR, {"plataforma": plataforma, "limite": MAX_COMENTARIOS})
        comentarios = _normalizar_comentarios(comentarios, plataforma, url)

        if comentarios:
            return {
                "status": "coletado",
                "metodo": "playwright_dom_visivel",
                "plataforma": plataforma,
                "url_origem": url,
                "quantidade": len(comentarios),
                "comentarios": comentarios,
                "alvo": alvo,
                "observacao": (
                    "Coleta best-effort de comentários visíveis após scroll e expansão de botões "
                    "'ver mais'. Comentários ocultos, removidos, paginados ou indisponíveis por "
                    "limitação da plataforma podem exigir requisição judicial/assessoria."
                ),
            }

        corpo = pagina.locator("body").inner_text(timeout=5000)
        if _LOGIN_RE.search(corpo):
            status = _status(
                "bloqueado_por_login",
                plataforma,
                url,
                "Comentários não coletados porque a plataforma exibiu barreira de login/sessão.",
            )
            status["alvo"] = alvo
            return status
        status = _status(
            "nao_encontrado",
            plataforma,
            url,
            "Nenhum comentário visível foi encontrado no DOM renderizado.",
        )
        status["alvo"] = alvo
        return status
    except Exception as exc:  # noqa: BLE001
        return _status("erro", plataforma, url, f"Falha na extração de comentários: {exc}")


def comentarios_para_txt(resultado: dict) -> str:
    """Gera versão texto legível dos comentários para leitura rápida/anexo."""
    linhas = [
        "COMENTÁRIOS COLETADOS - ProvaSocial Extract",
        f"Status: {resultado.get('status')}",
        f"Plataforma: {resultado.get('plataforma')}",
        f"URL: {resultado.get('url_origem')}",
        f"Quantidade: {resultado.get('quantidade', 0)}",
        "",
    ]
    for c in resultado.get("comentarios", []):
        linhas.extend(
            [
                f"[{c.get('indice')}] @{c.get('autor_username') or 'desconhecido'}",
                f"Nome: {c.get('autor_nome') or 'não identificado'}",
                f"Data/hora: {c.get('data_hora') or 'não disponível'}",
                f"Texto: {c.get('texto')}",
                "-" * 60,
            ]
        )
    alvo = resultado.get("alvo") or {}
    if alvo:
        linhas.extend(
            [
                "",
                "COMENTÁRIO ALVO",
                f"Trecho buscado: {alvo.get('trecho_busca') or 'não informado'}",
                f"Encontrado: {'sim' if alvo.get('encontrado') else 'não'}",
                f"Método: {alvo.get('metodo') or 'busca_direcionada'}",
                f"Scrolls executados: {alvo.get('scrolls_executados', 0)}",
            ]
        )
        if alvo.get("texto_encontrado"):
            linhas.append(f"Texto encontrado: {alvo['texto_encontrado']}")
        if alvo.get("artefatos"):
            linhas.append(f"Artefatos: {', '.join(alvo['artefatos'])}")
        if alvo.get("observacao"):
            linhas.append(f"Observação alvo: {alvo['observacao']}")
    if resultado.get("observacao"):
        linhas.extend(["", f"Observação: {resultado['observacao']}"])
    return "\n".join(linhas) + "\n"


def _expandir_comentarios(pagina) -> None:
    """Clica em botões comuns de expansão de comentários/respostas."""
    textos = (
        "Ver mais comentários",
        "Ver mais",
        "Ver respostas",
        "Carregar mais",
        "View more comments",
        "View more",
        "View replies",
        "Load more",
        "Show more replies",
        "Mostrar mais",
    )
    for _ in range(CLICKS_EXPANDIR):
        clicou = False
        for texto in textos:
            try:
                alvo = pagina.get_by_text(texto, exact=False).first
                if alvo.count() > 0:
                    alvo.click(timeout=1200)
                    pagina.wait_for_timeout(700)
                    clicou = True
            except Exception:  # noqa: BLE001
                continue
        if not clicou:
            break


def _scrollar(pagina) -> None:
    for _ in range(SCROLLS):
        try:
            pagina.mouse.wheel(0, 1400)
            pagina.wait_for_timeout(900)
            _expandir_comentarios(pagina)
        except Exception:  # noqa: BLE001
            break


def _buscar_comentario_alvo(
    pagina,
    plataforma: str,
    comentario_alvo: str | None,
    pasta: Path | None,
) -> dict | None:
    trecho = _limpar_texto(comentario_alvo)
    if not trecho:
        return None

    resultado = {
        "trecho_busca": trecho,
        "encontrado": False,
        "metodo": "playwright_dom_busca_direcionada",
        "scrolls_executados": 0,
        "artefatos": [],
        "ocr_status": "nao_executado",
        "observacao": (
            "Busca direcionada pelo trecho informado. A ausência de resultado não prova "
            "inexistência do comentário; ele pode estar apagado, oculto, paginado, filtrado "
            "por algoritmo ou bloqueado por login."
        ),
    }

    alvo_normalizado = _normalizar_busca(trecho)
    altura_anterior = 0
    ciclos_sem_crescer = 0

    for tentativa in range(SCROLLS_BUSCA_ALVO + 1):
        try:
            _expandir_comentarios(pagina)
            marcado = pagina.evaluate(
                _JS_MARCAR_ALVO,
                {"alvo": alvo_normalizado, "plataforma": plataforma},
            )
            resultado["scrolls_executados"] = tentativa
            if marcado and marcado.get("encontrado"):
                resultado.update(
                    {
                        "encontrado": True,
                        "texto_encontrado": marcado.get("texto"),
                        "autor_username": marcado.get("autor_username"),
                        "data_hora": marcado.get("data_hora"),
                        "observacao": (
                            "Comentário alvo localizado no conteúdo carregado. Foram preservados "
                            "o recorte visual e, quando disponível, o DOM do elemento."
                        ),
                    }
                )
                _salvar_artefatos_alvo(pagina, pasta, resultado, marcado)
                return resultado

            pagina.mouse.wheel(0, 1600)
            pagina.wait_for_timeout(900)
            altura = int(
                pagina.evaluate(
                    "() => document.documentElement.scrollHeight || document.body.scrollHeight || 0"
                )
            )
            if altura <= altura_anterior:
                ciclos_sem_crescer += 1
            else:
                ciclos_sem_crescer = 0
                altura_anterior = altura
            if ciclos_sem_crescer >= 6:
                break
        except Exception as exc:  # noqa: BLE001
            resultado["observacao"] = f"Busca do comentário alvo interrompida: {exc}"
            break

    return resultado


def _salvar_artefatos_alvo(pagina, pasta: Path | None, resultado: dict, marcado: dict) -> None:
    if pasta is None:
        return
    try:
        screenshot = "comentario_alvo_screenshot.png"
        pagina.locator('[data-provasocial-comentario-alvo="1"]').first.screenshot(
            path=str(pasta / screenshot),
            timeout=3000,
        )
        resultado["artefatos"].append(screenshot)
        ocr = _ocr_imagem(pasta / screenshot)
        resultado["ocr_status"] = ocr["status"]
        if ocr.get("texto"):
            ocr_arquivo = "comentario_alvo_ocr.txt"
            (pasta / ocr_arquivo).write_text(ocr["texto"], encoding="utf-8")
            resultado["ocr_texto"] = ocr["texto"][:2000]
            resultado["artefatos"].append(ocr_arquivo)
    except Exception as exc:  # noqa: BLE001
        resultado["observacao"] = (
            f"{resultado.get('observacao', '')} Falha ao salvar screenshot do alvo: {exc}"
        ).strip()

    html_elemento = marcado.get("html")
    if html_elemento:
        try:
            dom_arquivo = "comentario_alvo_dom.html"
            (pasta / dom_arquivo).write_text(str(html_elemento), encoding="utf-8")
            resultado["artefatos"].append(dom_arquivo)
        except OSError as exc:
            resultado["observacao"] = (
                f"{resultado.get('observacao', '')} Falha ao salvar DOM do alvo: {exc}"
            ).strip()


def _ocr_imagem(caminho: Path) -> dict:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return {
            "status": "indisponivel",
            "observacao": "OCR não executado: instale pytesseract e o binário Tesseract para habilitar.",
        }
    try:
        texto = pytesseract.image_to_string(Image.open(caminho), lang="por+eng").strip()
        return {"status": "coletado" if texto else "sem_texto", "texto": texto}
    except Exception as exc:  # noqa: BLE001
        return {"status": "erro", "observacao": f"OCR falhou: {exc}"}


def _normalizar_comentarios(comentarios: list[dict], plataforma: str, url: str) -> list[dict]:
    vistos: set[str] = set()
    limpos: list[dict] = []
    for bruto in comentarios or []:
        texto = _limpar_texto(bruto.get("texto"))
        if not texto or len(texto) < 2:
            continue
        chave = f"{bruto.get('autor_username') or bruto.get('autor_nome') or ''}|{texto[:180]}"
        if chave in vistos:
            continue
        vistos.add(chave)
        limpos.append(
            {
                "indice": len(limpos) + 1,
                "plataforma": plataforma,
                "autor_username": _limpar_autor(bruto.get("autor_username")),
                "autor_nome": _limpar_texto(bruto.get("autor_nome")),
                "texto": texto,
                "data_hora": _limpar_texto(bruto.get("data_hora")),
                "url_origem": url,
                "metodo": bruto.get("metodo_dom") or "playwright_dom_visivel",
            }
        )
        if len(limpos) >= MAX_COMENTARIOS:
            break
    return limpos


def _limpar_texto(valor) -> str | None:
    if not isinstance(valor, str):
        return None
    texto = re.sub(r"\s+", " ", valor).strip()
    if not texto:
        return None
    # Remove textos muito genéricos de interface.
    rejeitar = (
        "log in",
        "sign up",
        "entrar",
        "cadastre-se",
        "curtir",
        "responder",
        "compartilhar",
        "ver tradução",
        "see translation",
        "ver respostas",
        "view replies",
        "mais",
        "more",
        "seguir",
        "follow",
        "enviar",
        "send",
        "privacidade",
        "localizações",
        "localizacoes",
        "instagram lite",
        "meta ai",
        "meta verified",
        "português (brasil)",
        "portugues (brasil)",
    )
    if texto.lower() in rejeitar:
        return None
    if _CURTIDAS_RE.match(texto):
        return None
    if _TEMPO_RELATIVO_RE.match(texto):
        return None
    if _RESPOSTAS_RE.match(texto):
        return None
    if _FOOTER_RE.match(texto):
        return None
    return texto[:2000]


def _limpar_autor(valor) -> str | None:
    texto = _limpar_texto(valor)
    if not texto:
        return None
    texto = texto.lstrip("@")
    if " " in texto and len(texto.split()) > 3:
        return None
    return texto[:80]


def _normalizar_busca(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", texto).strip().lower()


def _status(status: str, plataforma: str, url: str, observacao: str) -> dict:
    return {
        "status": status,
        "metodo": "playwright_dom_visivel",
        "plataforma": plataforma,
        "url_origem": url,
        "quantidade": 0,
        "comentarios": [],
        "alvo": None,
        "observacao": observacao,
    }


_JS_MARCAR_ALVO = r"""
({ alvo, plataforma }) => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const norm = (s) => clean(s)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && st.display !== "none";
  };
  const authorFrom = (el) => {
    const link = el.querySelector("a[href^='/'], a[href*='instagram.com/'], a[href*='facebook.com/'], a[href*='x.com/']");
    return clean(link?.textContent || link?.getAttribute("href") || "");
  };
  const timeFrom = (el) => el.querySelector("time")?.getAttribute("datetime") || clean(el.querySelector("time")?.textContent);
  const selectorsByPlatform = {
    youtube: ["ytd-comment-thread-renderer", "ytd-comment-view-model"],
    x: ['article[data-testid="tweet"]'],
    instagram: ["article ul li", "main ul li", "div[role='dialog'] ul li", "span[dir='auto']"],
    facebook: ["div[role='article']", "[aria-label*='comment' i]", "[aria-label*='coment' i]"],
  };
  const selectors = [
    ...(selectorsByPlatform[plataforma] || []),
    "li",
    "article",
    "div[role='article']",
  ];
  document.querySelectorAll("[data-provasocial-comentario-alvo='1']").forEach((el) => {
    el.removeAttribute("data-provasocial-comentario-alvo");
    el.style.outline = "";
  });

  for (const selector of selectors) {
    for (const el of Array.from(document.querySelectorAll(selector))) {
      if (!visible(el)) continue;
      const text = clean(el.innerText || el.textContent);
      if (!text || !norm(text).includes(alvo)) continue;
      const container = el.closest("li, article, ytd-comment-thread-renderer, ytd-comment-view-model, div[role='article']") || el;
      container.setAttribute("data-provasocial-comentario-alvo", "1");
      container.style.outline = "3px solid #e94560";
      container.scrollIntoView({ block: "center", inline: "nearest" });
      return {
        encontrado: true,
        texto: clean(container.innerText || container.textContent).slice(0, 3000),
        autor_username: authorFrom(container),
        data_hora: timeFrom(container),
        html: container.outerHTML,
      };
    }
  }
  return { encontrado: false };
}
"""


_JS_EXTRATOR = r"""
({ plataforma, limite }) => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const uniq = (arr) => Array.from(new Set(arr.filter(Boolean).map(clean)));

  function visible(el) {
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && st.display !== "none";
  }

  function fromYouTube() {
    return Array.from(document.querySelectorAll("ytd-comment-thread-renderer")).map((el) => ({
      autor_username: clean(el.querySelector("#author-text")?.textContent),
      autor_nome: clean(el.querySelector("#author-text")?.textContent),
      texto: clean(el.querySelector("#content-text")?.textContent),
      data_hora: clean(el.querySelector("#published-time-text")?.textContent),
    }));
  }

  function fromX() {
    return Array.from(document.querySelectorAll('article[data-testid="tweet"]')).map((el) => {
      const textBlocks = uniq(Array.from(el.querySelectorAll('[data-testid="tweetText"], div[lang]')).map((n) => n.textContent));
      const users = uniq(Array.from(el.querySelectorAll('a[href^="/"]')).map((a) => a.getAttribute("href")?.split("/")[1]));
      const time = el.querySelector("time")?.getAttribute("datetime") || clean(el.querySelector("time")?.textContent);
      return { autor_username: users[0], autor_nome: users[0], texto: textBlocks.join(" "), data_hora: time };
    });
  }

  function fromInstagram() {
    const isUi = (t) => /^(Curtir|Responder|Ver tradução|See translation|Ver respostas|View replies|Mais|More|Seguir|Follow|Enviar|Send|Compartilhar|Share|Privacidade|Localizações|Instagram Lite|Meta AI|Meta Verified|Português \(Brasil\)|©\s*\d{4}\s+Instagram from Meta)$/i.test(clean(t));
    const isEngagement = (t) => /^\d+([.,]\d+)?\s*(curtidas?|likes?)$/i.test(clean(t));
    const isRelativeTime = (t) => /^(há\s+)?\d+\s*(s|seg|segundos?|min|minutos?|h|horas?|d|dias?|sem|semanas?)$/i.test(clean(t));
    const isReplies = (t) => /^(ver|view)\s+(todas?\s+)?(as\s+)?\d+\s+(respostas?|replies)$/i.test(clean(t));
    const isNoise = (t) => !clean(t) || isUi(t) || isEngagement(t) || isRelativeTime(t) || isReplies(t);
    const looksUser = (t) => /^[A-Za-z0-9._]{2,30}$/.test(clean(t));
    const findUserNear = (node) => {
      let cur = node;
      for (let i = 0; i < 7 && cur; i++) {
        const links = Array.from(cur.querySelectorAll ? cur.querySelectorAll("a[href^='/']") : []);
        const user = links
          .map((a) => clean(a.textContent) || clean(a.getAttribute("href") || "").split("/").filter(Boolean)[0])
          .find((t) => t && looksUser(t) && !isUi(t));
        if (user) return user.replace(/^@/, "");
        cur = cur.parentElement;
      }
      return "";
    };

    const structured = Array.from(document.querySelectorAll("article ul li, main ul li, div[role='dialog'] ul li"))
      .filter(visible);
    const fromStructured = structured.map((el) => {
      const links = Array.from(el.querySelectorAll("a[href^='/']"));
      const user = links.map((a) => clean(a.textContent)).find((t) => t && !/^(Curtir|Responder|Ver|View)$/i.test(t));
      const time = el.querySelector("time")?.getAttribute("datetime") || clean(el.querySelector("time")?.textContent);
      const spans = uniq(Array.from(el.querySelectorAll("span")).map((s) => s.textContent));
      const texto = spans.filter((s) => s !== user && !isNoise(s) && !looksUser(s)).join(" ");
      return { autor_username: user, autor_nome: user, texto, data_hora: time, metodo_dom: "instagram_structured" };
    });

    // Fallback para DOM ofuscado do Instagram/Reels: comentários aparecem como span[dir="auto"].
    const spanCandidates = Array.from(document.querySelectorAll('span[dir="auto"]'))
      .filter(visible)
      .map((span) => {
        const texto = clean(span.textContent);
        if (!texto || texto.length < 2 || isNoise(texto) || looksUser(texto)) return null;
        const autor = findUserNear(span);
        const container = span.closest("li, article, div[role='dialog'], div");
        const time = container?.querySelector("time")?.getAttribute("datetime") || clean(container?.querySelector("time")?.textContent);
        return { autor_username: autor, autor_nome: autor, texto, data_hora: time, metodo_dom: "instagram_span_dir_auto" };
      })
      .filter(Boolean);

    return [...fromStructured, ...spanCandidates];
  }

  function fromFacebook() {
    const candidates = Array.from(document.querySelectorAll("div[role='article'], [aria-label*='comment' i], [aria-label*='coment' i]"))
      .filter(visible);
    return candidates.map((el) => {
      const text = clean(el.innerText || el.textContent);
      const lines = text.split("\n").map(clean).filter(Boolean);
      return { autor_username: lines[0], autor_nome: lines[0], texto: lines.slice(1).join(" "), data_hora: "" };
    });
  }

  function generic() {
    const candidates = Array.from(document.querySelectorAll("li, article, div[role='article']"))
      .filter(visible);
    return candidates.map((el) => {
      const text = clean(el.innerText || el.textContent);
      const lines = text.split("\n").map(clean).filter(Boolean);
      return { autor_username: lines[0], autor_nome: lines[0], texto: lines.slice(1).join(" ") || text, data_hora: "" };
    });
  }

  let out = [];
  if (plataforma === "youtube") out = fromYouTube();
  else if (plataforma === "x") out = fromX();
  else if (plataforma === "instagram") out = fromInstagram();
  else if (plataforma === "facebook") out = fromFacebook();
  if (!out.length) out = generic();

  return out
    .filter((c) => clean(c.texto).length > 1)
    .slice(0, limite);
}
"""
