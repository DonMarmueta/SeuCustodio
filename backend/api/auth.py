"""Autenticação: hash de senha (PBKDF2) e tokens de sessão (JWT em cookie).

Evita dependências nativas (bcrypt) usando hashlib.pbkdf2_hmac da stdlib.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.db import get_db
from backend.api.models import Usuario
from backend.config import SECRET_KEY, TOKEN_EXPIRA_HORAS

COOKIE_NOME = "ps_token"
_ITERACOES = 240_000


# --------------------------------------------------------------------------- #
# Senhas                                                                       #
# --------------------------------------------------------------------------- #
def hash_senha(senha: str) -> str:
    """Gera 'pbkdf2_sha256$iteracoes$salt$hash'."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), _ITERACOES)
    return f"pbkdf2_sha256${_ITERACOES}${salt}${dk.hex()}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        _, iteracoes, salt, hash_hex = armazenado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), int(iteracoes))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# Tokens                                                                       #
# --------------------------------------------------------------------------- #
def criar_token(usuario_id: int) -> str:
    payload = {
        "sub": str(usuario_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRA_HORAS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _decodificar(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Dependências FastAPI                                                         #
# --------------------------------------------------------------------------- #
def usuario_opcional(
    ps_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Retorna o usuário logado a partir do cookie, ou None."""
    if not ps_token:
        return None
    uid = _decodificar(ps_token)
    if uid is None:
        return None
    return db.get(Usuario, uid)


def usuario_atual(usuario: Usuario | None = Depends(usuario_opcional)) -> Usuario:
    """Exige autenticação; lança 401 se não logado."""
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )
    return usuario
