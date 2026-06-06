"""Configuração do banco de dados (SQLAlchemy 2.0 + SQLite por padrão)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL

# check_same_thread=False permite uso do SQLite a partir de threads de background
# (o job de captura roda em thread separada).
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Cria as tabelas (idempotente)."""
    from backend.api import models  # noqa: F401 — registra os modelos

    Base.metadata.create_all(bind=engine)
    _migrar_sqlite_simples()


def _migrar_sqlite_simples() -> None:
    """Adiciona colunas novas em bancos SQLite já criados no MVP.

    O projeto ainda não usa Alembic; esta rotina cobre apenas migrações
    pequenas e compatíveis com SQLite local.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspetor = inspect(engine)
    if "coletas" not in inspetor.get_table_names():
        return
    colunas = {coluna["name"] for coluna in inspetor.get_columns("coletas")}
    alteracoes = []
    if "comentario_alvo" not in colunas:
        alteracoes.append("ALTER TABLE coletas ADD COLUMN comentario_alvo TEXT")

    if not alteracoes:
        return
    with engine.begin() as conn:
        for sql in alteracoes:
            conn.execute(text(sql))


def get_db() -> Iterator[Session]:
    """Dependência FastAPI: fornece uma sessão por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
