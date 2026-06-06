"""Cadeia de custódia conforme CPP art. 158-A a 158-F (Lei 13.964/19).

Registra as etapas legais da prova de forma encadeada por hash. Cada etapa
referencia o hash da anterior, criando uma trilha verificável e à prova de
adulteração posterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.custodia import hashing
from backend.custodia.timestamp import agora

# Etapas previstas no art. 158-B do CPP. Nem todas se aplicam à coleta digital
# automatizada, mas registramos as pertinentes ao fluxo da ferramenta.
ETAPAS_VALIDAS = (
    "reconhecimento",
    "isolamento",
    "fixacao",
    "coleta",
    "acondicionamento",
    "transporte",
    "recebimento",
    "processamento",
    "armazenamento",
    "descarte",
)


@dataclass
class CadeiaCustodia:
    """Acumula as etapas da cadeia de custódia de uma coleta."""

    coleta_id: str
    url_alvo: str
    plataforma: str
    etapas: list[dict] = field(default_factory=list)

    def registrar(self, etapa: str, ator: str, descricao: str, hash_conteudo: str | None = None) -> dict:
        """Registra uma etapa, encadeando-a à anterior.

        :param etapa: uma das ETAPAS_VALIDAS.
        :param ator: quem executou (ex.: 'worker@servidor', nome do analista).
        :param descricao: descrição livre do que foi feito.
        :param hash_conteudo: hash do artefato envolvido (se houver).
        """
        if etapa not in ETAPAS_VALIDAS:
            raise ValueError(f"Etapa inválida: {etapa}. Use uma de {ETAPAS_VALIDAS}.")

        hash_anterior = self.etapas[-1]["hash_atual"] if self.etapas else None
        # O elo da cadeia mistura: hash anterior + hash do conteúdo + carimbo de tempo.
        t = agora()
        material = (hash_conteudo or "") + t["utc"] + etapa + ator
        hash_etapa = hashing.hash_texto(material)
        hash_atual = hashing.encadear(hash_anterior, hash_etapa)

        registro = {
            "indice": len(self.etapas) + 1,
            "etapa": etapa,
            "ator": ator,
            "descricao": descricao,
            "momento_utc": t["utc"],
            "momento_brasilia": t["brasilia"],
            "hash_conteudo": hash_conteudo,
            "hash_anterior": hash_anterior,
            "hash_atual": hash_atual,
        }
        self.etapas.append(registro)
        return registro

    def hash_final(self) -> str | None:
        """Retorna o hash do último elo (âncora da cadeia)."""
        return self.etapas[-1]["hash_atual"] if self.etapas else None

    def para_dict(self) -> dict:
        return {
            "coleta_id": self.coleta_id,
            "url_alvo": self.url_alvo,
            "plataforma": self.plataforma,
            "etapas": self.etapas,
            "hash_final_cadeia": self.hash_final(),
        }

    @staticmethod
    def verificar(dados: dict) -> tuple[bool, list[str]]:
        """Reverifica a integridade do encadeamento de uma cadeia salva.

        Retorna (ok, problemas).
        """
        problemas: list[str] = []
        anterior: str | None = None
        for reg in dados.get("etapas", []):
            if reg.get("hash_anterior") != anterior:
                problemas.append(
                    f"Etapa {reg.get('indice')}: hash_anterior não confere com o elo prévio."
                )
            esperado = hashing.encadear(
                reg.get("hash_anterior"),
                _recomputar_hash_etapa(reg),
            )
            if reg.get("hash_atual") != esperado:
                problemas.append(
                    f"Etapa {reg.get('indice')}: hash_atual recalculado não confere."
                )
            anterior = reg.get("hash_atual")
        return (len(problemas) == 0, problemas)


def _recomputar_hash_etapa(reg: dict) -> str:
    """Recompõe o hash interno de uma etapa a partir dos campos salvos."""
    material = (reg.get("hash_conteudo") or "") + reg.get("momento_utc", "") + reg.get("etapa", "") + reg.get("ator", "")
    return hashing.hash_texto(material)
