"""Modelos de dados da camada SaaS."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.api.db import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(255), default="")
    senha_hash: Mapped[str] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    coletas: Mapped[list["Coleta"]] = relationship(back_populates="usuario")


class Coleta(Base):
    __tablename__ = "coletas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    url_alvo: Mapped[str] = mapped_column(Text)
    plataforma: Mapped[str] = mapped_column(String(40), default="generico")
    comentario_alvo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estados: aguardando_pagamento | pago | capturando | concluido | erro
    status: Mapped[str] = mapped_column(String(30), default="aguardando_pagamento", index=True)
    nivel: Mapped[str] = mapped_column(String(20), default="basico")  # basico|notarial|pericial

    codigo_verificacao: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    pasta: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_manifesto: Mapped[str | None] = mapped_column(String(128), nullable=True)
    erro_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    pago_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capturado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="coletas")
    pagamento: Mapped["Pagamento"] = relationship(back_populates="coleta", uselist=False)


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coleta_id: Mapped[int] = mapped_column(ForeignKey("coletas.id"), index=True)
    gateway: Mapped[str] = mapped_column(String(30), default="mercadopago")
    valor: Mapped[float] = mapped_column(Float)

    # Estados: pendente | aprovado | recusado | cancelado
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    ref_externa: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)

    # Dados do Pix para exibir ao cliente.
    qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)        # copia-e-cola
    qr_code_base64: Mapped[str | None] = mapped_column(Text, nullable=True)  # imagem

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    coleta: Mapped["Coleta"] = relationship(back_populates="pagamento")


class Upsell(Base):
    """Solicitação de serviço especializado (assessoria) sobre uma coleta.

    É o 'gancho' acionado quando a coleta automatizada atinge seus limites
    (ex.: identificação de usuário no Instagram/Facebook) ou quando o cliente
    quer força probatória reforçada.
    """

    __tablename__ = "upsells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coleta_id: Mapped[int] = mapped_column(ForeignKey("coletas.id"), index=True)

    # tipo: assessoria | notarial | pericial
    tipo: Mapped[str] = mapped_column(String(20), index=True)
    # status: solicitado | em_contato | em_andamento | concluido | cancelado
    status: Mapped[str] = mapped_column(String(20), default="solicitado", index=True)

    contato: Mapped[str] = mapped_column(String(255), default="")
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    fornecedor_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    coleta: Mapped["Coleta"] = relationship()
