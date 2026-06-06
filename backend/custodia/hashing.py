"""Cálculo de hashes criptográficos dos artefatos de evidência.

O hash é a âncora de integridade de toda a prova: qualquer alteração de 1 byte
em um artefato muda o hash e quebra a verificação.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Lê arquivos em blocos para suportar mídias grandes sem estourar memória.
_TAMANHO_BLOCO = 1024 * 1024  # 1 MiB


def hash_bytes(dados: bytes, algoritmo: str = "sha256") -> str:
    """Retorna o hash hexadecimal de uma sequência de bytes."""
    h = hashlib.new(algoritmo)
    h.update(dados)
    return h.hexdigest()


def hash_texto(texto: str, algoritmo: str = "sha256") -> str:
    """Retorna o hash hexadecimal de um texto (codificado em UTF-8)."""
    return hash_bytes(texto.encode("utf-8"), algoritmo)


def hash_arquivo(caminho: str | Path, algoritmo: str = "sha256") -> str:
    """Retorna o hash hexadecimal do conteúdo de um arquivo."""
    h = hashlib.new(algoritmo)
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(_TAMANHO_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def encadear(hash_anterior: str | None, hash_atual: str, algoritmo: str = "sha256") -> str:
    """Encadeia dois hashes (estilo blockchain leve).

    Cada etapa/artefato referencia o hash do anterior, de modo que a remoção ou
    reordenação de qualquer elo quebra a cadeia inteira.
    """
    base = (hash_anterior or "") + hash_atual
    return hash_texto(base, algoritmo)
