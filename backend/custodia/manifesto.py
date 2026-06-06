"""Manifesto de integridade da coleta.

Reúne os hashes de todos os artefatos + a cadeia de custódia em um único
documento JSON, encadeado e datado. O `hash_manifesto` final é o que vai no
laudo e no portal público de verificação.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend import __version__
from backend.config import ALGORITMO_HASH
from backend.custodia import hashing
from backend.custodia.timestamp import agora


def construir(
    coleta_id: str,
    codigo_verificacao: str,
    url_alvo: str,
    plataforma: str,
    analista: str,
    caso: str | None,
    artefatos: list[dict],
    metadados: dict,
    cadeia: dict,
) -> dict:
    """Monta o dicionário do manifesto e calcula seu hash final.

    :param artefatos: lista de dicts {nome, tipo, arquivo, sha256, tamanho}.
    """
    # Encadeia os hashes dos artefatos em ordem estável.
    encadeado: str | None = None
    for art in artefatos:
        encadeado = hashing.encadear(encadeado, art["sha256"])

    corpo = {
        "ferramenta": "ProvaSocial-Extract",
        "versao": __version__,
        "coleta_id": coleta_id,
        "codigo_verificacao": codigo_verificacao,
        "url_alvo": url_alvo,
        "plataforma": plataforma,
        "analista": analista,
        "caso": caso,
        "gerado_em": agora(),
        "algoritmo_hash": ALGORITMO_HASH,
        "artefatos": artefatos,
        "hash_encadeado_artefatos": encadeado,
        "hash_final_cadeia": cadeia.get("hash_final_cadeia"),
        "metadados": metadados,
    }

    # O hash do manifesto cobre todo o corpo de forma determinística.
    corpo_canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
    corpo["hash_manifesto"] = hashing.hash_texto(corpo_canonico)
    return corpo


def salvar(manifesto: dict, caminho: str | Path) -> None:
    """Grava o manifesto em JSON (UTF-8, indentado)."""
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)


def carregar(caminho: str | Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def verificar(manifesto: dict, pasta: str | Path) -> tuple[bool, list[str]]:
    """Reverifica um manifesto contra os arquivos em disco.

    Confere: (1) hash de cada artefato, (2) encadeamento dos artefatos,
    (3) hash do próprio manifesto. Retorna (ok, problemas).
    """
    pasta = Path(pasta)
    problemas: list[str] = []
    algoritmo = manifesto.get("algoritmo_hash", "sha256")

    # 1) hash de cada artefato em disco
    encadeado: str | None = None
    for art in manifesto.get("artefatos", []):
        arquivo = pasta / art["arquivo"]
        if not arquivo.exists():
            problemas.append(f"Artefato ausente: {art['arquivo']}")
            encadeado = hashing.encadear(encadeado, art["sha256"])
            continue
        real = hashing.hash_arquivo(arquivo, algoritmo)
        if real != art["sha256"]:
            problemas.append(
                f"Hash divergente em {art['arquivo']}: esperado {art['sha256'][:16]}..., obtido {real[:16]}..."
            )
        encadeado = hashing.encadear(encadeado, art["sha256"])

    # 2) encadeamento dos artefatos
    if encadeado != manifesto.get("hash_encadeado_artefatos"):
        problemas.append("Encadeamento de artefatos não confere.")

    # 3) hash do manifesto
    corpo = {k: v for k, v in manifesto.items() if k != "hash_manifesto"}
    corpo_canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
    esperado = hashing.hash_texto(corpo_canonico)
    if esperado != manifesto.get("hash_manifesto"):
        problemas.append("Hash do manifesto não confere (documento possivelmente adulterado).")

    return (len(problemas) == 0, problemas)
