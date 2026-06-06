"""Aplicação FastAPI do ProvaSocial-Extract (camada SaaS, Fase 2).

Sobe com:  uvicorn backend.api.app:app --reload
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api import mercadopago
from backend.api.auth import (
    COOKIE_NOME,
    conferir_senha,
    criar_token,
    hash_senha,
    usuario_atual,
    usuario_opcional,
)
from backend.api.db import get_db, init_db
from backend.api.models import Coleta, Pagamento, Upsell, Usuario
from backend.api.rotas_pagamentos import router as router_pagamentos
from backend.banner import imprimir_banner
from backend.captura.base import identificar_plataforma
from backend.config import MODO_SIMULADO, SERVICOS_ASSESSORIA, VALOR_COLETA
from backend.custodia import manifesto as mod_manifesto
from backend.custodia.cadeia import CadeiaCustodia

RAIZ_API = Path(__file__).resolve().parent
TEMPLATES_DIR = RAIZ_API.parent.parent / "templates"
STATIC_DIR = RAIZ_API.parent.parent / "static"

app = FastAPI(title="ProvaSocial — Extract", version="0.2.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(router_pagamentos)

# Cria as tabelas na importação (idempotente) — garante o schema mesmo quando o
# evento de startup não é disparado (ex.: TestClient sem context manager).
init_db()


@app.on_event("startup")
def _startup() -> None:
    imprimir_banner()
    init_db()


def _render(name: str, ctx: dict, **kwargs):
    """Renderiza um template usando a assinatura nova do Starlette (request primeiro)."""
    return templates.TemplateResponse(request=ctx["request"], name=name, context=ctx, **kwargs)


def _ctx(request: Request, usuario: Usuario | None, **extra) -> dict:
    base = {
        "request": request,
        "usuario": usuario,
        "valor": f"{VALOR_COLETA:.2f}".replace(".", ","),
        "modo_simulado": MODO_SIMULADO,
        "servicos_assessoria": SERVICOS_ASSESSORIA,
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------- #
# Páginas públicas                                                             #
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def landing(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _render("landing.html", _ctx(request, usuario))


@app.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _render("registro.html", _ctx(request, usuario))


@app.post("/registro")
def registro(
    request: Request,
    nome: str = Form(""),
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if db.scalars(select(Usuario).where(Usuario.email == email)).first():
        return _render(
            "registro.html",
            _ctx(request, None, erro="Já existe uma conta com este e-mail."),
            status_code=400,
        )
    usuario = Usuario(email=email, nome=nome.strip(), senha_hash=hash_senha(senha))
    db.add(usuario)
    db.commit()
    resp = RedirectResponse("/painel", status_code=303)
    resp.set_cookie(COOKIE_NOME, criar_token(usuario.id), httponly=True, samesite="lax")
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _render("login.html", _ctx(request, usuario))


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    usuario = db.scalars(select(Usuario).where(Usuario.email == email)).first()
    if usuario is None or not conferir_senha(senha, usuario.senha_hash):
        return _render(
            "login.html",
            _ctx(request, None, erro="E-mail ou senha inválidos."),
            status_code=401,
        )
    resp = RedirectResponse("/painel", status_code=303)
    resp.set_cookie(COOKIE_NOME, criar_token(usuario.id), httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE_NOME)
    return resp


# --------------------------------------------------------------------------- #
# Área autenticada                                                             #
# --------------------------------------------------------------------------- #
@app.get("/painel", response_class=HTMLResponse)
def painel(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    coletas = db.scalars(
        select(Coleta).where(Coleta.usuario_id == usuario.id).order_by(Coleta.criado_em.desc())
    ).all()
    return _render("painel.html", _ctx(request, usuario, coletas=coletas))


@app.get("/coletar", response_class=HTMLResponse)
def coletar_form(request: Request, usuario: Usuario = Depends(usuario_atual)):
    return _render("nova_coleta.html", _ctx(request, usuario))


@app.post("/coletar")
def coletar_criar(
    request: Request,
    url: str = Form(...),
    comentario_alvo: str = Form(""),
    nivel: str = Form("basico"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    url = url.strip()
    comentario_alvo = comentario_alvo.strip()
    if nivel not in ("basico", "pericial"):
        nivel = "basico"
    if not url.lower().startswith(("http://", "https://")):
        return _render(
            "nova_coleta.html",
            _ctx(request, usuario, erro="Informe uma URL válida (http/https)."),
            status_code=400,
        )

    coleta = Coleta(
        usuario_id=usuario.id,
        url_alvo=url,
        plataforma=identificar_plataforma(url),
        comentario_alvo=comentario_alvo or None,
        nivel=nivel,
        status="aguardando_pagamento",
    )
    db.add(coleta)
    db.commit()

    pix = mercadopago.criar_pix(
        valor=VALOR_COLETA,
        descricao=f"Coleta forense — {coleta.plataforma}",
        email_pagador=usuario.email,
        referencia=str(coleta.id),
    )
    if not pix["ok"]:
        coleta.status = "erro"
        coleta.erro_msg = pix.get("erro")
        db.commit()
        return _render(
            "nova_coleta.html",
            _ctx(request, usuario, erro=f"Falha ao gerar Pix: {pix.get('erro')}"),
            status_code=502,
        )

    pagamento = Pagamento(
        coleta_id=coleta.id,
        gateway="mercadopago",
        valor=VALOR_COLETA,
        status=pix["status"],
        ref_externa=pix["ref_externa"],
        qr_code=pix.get("qr_code"),
        qr_code_base64=pix.get("qr_code_base64"),
    )
    db.add(pagamento)
    db.commit()

    return RedirectResponse(f"/pagamento/{coleta.id}", status_code=303)


@app.get("/pagamento/{coleta_id}", response_class=HTMLResponse)
def pagamento_pagina(
    coleta_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")
    return _render(
        "pagamento.html", _ctx(request, usuario, coleta=coleta, pagamento=coleta.pagamento)
    )


@app.get("/coleta/{coleta_id}", response_class=HTMLResponse)
def coleta_detalhe(
    coleta_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")

    arquivos: list[str] = []
    metadados: dict = {}
    identificacao_limitada = False
    if coleta.pasta and Path(coleta.pasta).exists():
        pasta = Path(coleta.pasta)
        arquivos = [p.name for p in pasta.iterdir() if p.is_file()]
        meta_file = pasta / "metadados.json"
        if meta_file.exists():
            metadados = json.loads(meta_file.read_text(encoding="utf-8"))
            identificacao_limitada = bool(metadados.get("identificacao_requer_assessoria"))

    upsells = db.scalars(
        select(Upsell).where(Upsell.coleta_id == coleta.id).order_by(Upsell.criado_em.desc())
    ).all()

    return _render(
        "coleta.html",
        _ctx(
            request,
            usuario,
            coleta=coleta,
            arquivos=arquivos,
            metadados=metadados,
            identificacao_limitada=identificacao_limitada,
            upsells=upsells,
        ),
    )


@app.get("/coleta/{coleta_id}/status")
def coleta_status(
    coleta_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Endpoint de polling usado pelas páginas para atualizar o status."""
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")
    return {
        "status": coleta.status,
        "codigo": coleta.codigo_verificacao,
        "erro": coleta.erro_msg,
    }


@app.get("/coleta/{coleta_id}/download/{arquivo}")
def coleta_download(
    coleta_id: int,
    arquivo: str,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id or not coleta.pasta:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    pasta = Path(coleta.pasta).resolve()
    alvo = (pasta / arquivo).resolve()
    # Impede path traversal: o alvo precisa estar dentro da pasta da coleta.
    if not str(alvo).startswith(str(pasta)) or not alvo.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(str(alvo), filename=alvo.name)


# --------------------------------------------------------------------------- #
# Upsell / serviços complementares                                            #
# --------------------------------------------------------------------------- #
@app.post("/coleta/{coleta_id}/assessoria")
def solicitar_assessoria(
    coleta_id: int,
    tipo: str = Form("assessoria"),
    contato: str = Form(""),
    observacao: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Registra solicitação de serviço especializado sobre uma coleta."""
    coleta = db.get(Coleta, coleta_id)
    if coleta is None or coleta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Coleta não encontrada.")
    if tipo not in SERVICOS_ASSESSORIA:
        raise HTTPException(status_code=400, detail="Tipo de serviço inválido.")

    upsell = Upsell(
        coleta_id=coleta.id,
        tipo=tipo,
        status="solicitado",
        contato=contato.strip(),
        observacao=observacao.strip() or None,
    )
    db.add(upsell)
    db.commit()
    return RedirectResponse(f"/coleta/{coleta.id}/assessoria/{upsell.id}", status_code=303)


@app.get("/coleta/{coleta_id}/assessoria/{upsell_id}", response_class=HTMLResponse)
def assessoria_confirmacao(
    coleta_id: int,
    upsell_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    coleta = db.get(Coleta, coleta_id)
    upsell = db.get(Upsell, upsell_id)
    if (
        coleta is None
        or coleta.usuario_id != usuario.id
        or upsell is None
        or upsell.coleta_id != coleta.id
    ):
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    servico = SERVICOS_ASSESSORIA[upsell.tipo]
    return _render(
        "assessoria_confirmacao.html",
        _ctx(request, usuario, coleta=coleta, upsell=upsell, servico=servico),
    )


# --------------------------------------------------------------------------- #
# Portal público de verificação                                               #
# --------------------------------------------------------------------------- #
@app.get("/verificar", response_class=HTMLResponse)
def verificar_form(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _render("verificar.html", _ctx(request, usuario))


@app.get("/verificar/{codigo}", response_class=HTMLResponse)
def verificar_codigo(
    codigo: str,
    request: Request,
    usuario: Usuario | None = Depends(usuario_opcional),
    db: Session = Depends(get_db),
):
    resultado = _verificar_por_codigo(codigo, db)
    return _render(
        "verificar.html", _ctx(request, usuario, resultado=resultado, codigo=codigo)
    )


@app.get("/api/verificar/{codigo}")
def api_verificar(codigo: str, db: Session = Depends(get_db)):
    resultado = _verificar_por_codigo(codigo, db)
    if resultado is None:
        return JSONResponse({"encontrado": False}, status_code=404)
    return resultado


def _verificar_por_codigo(codigo: str, db: Session) -> dict | None:
    """Localiza a coleta pelo código e reverifica a integridade em disco."""
    coleta = db.scalars(
        select(Coleta).where(Coleta.codigo_verificacao == codigo.strip().upper())
    ).first()
    if coleta is None or not coleta.pasta:
        return None

    pasta = Path(coleta.pasta)
    arquivo_manifesto = pasta / "manifesto.json"
    if not arquivo_manifesto.exists():
        return None

    manifesto = mod_manifesto.carregar(arquivo_manifesto)
    ok_man, problemas_man = mod_manifesto.verificar(manifesto, pasta)

    ok_cad, problemas_cad = True, []
    arquivo_cadeia = pasta / "cadeia_custodia.json"
    if arquivo_cadeia.exists():
        cadeia = json.loads(arquivo_cadeia.read_text(encoding="utf-8"))
        ok_cad, problemas_cad = CadeiaCustodia.verificar(cadeia)

    return {
        "encontrado": True,
        "integro": ok_man and ok_cad,
        "problemas": problemas_man + problemas_cad,
        "coleta_id": manifesto.get("coleta_id"),
        "url_alvo": manifesto.get("url_alvo"),
        "plataforma": manifesto.get("plataforma"),
        "coletado_em": manifesto.get("gerado_em", {}).get("brasilia"),
        "hash_manifesto": manifesto.get("hash_manifesto"),
        "qtd_artefatos": len(manifesto.get("artefatos", [])),
    }
