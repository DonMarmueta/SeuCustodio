"""Verificador independente de integridade de uma coleta.

Pode ser executado por qualquer terceiro (advogado, perito da parte contrária,
juízo) para confirmar que os artefatos de uma coleta não foram alterados após a
captura. Não depende de rede nem de chave secreta — apenas recalcula os hashes.

Uso:
    python verificar.py "evidencias/EV-001_ABCDEF123456"
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.custodia import manifesto as mod_manifesto
from backend.custodia.cadeia import CadeiaCustodia


def verificar_pasta(pasta: str | Path) -> int:
    pasta = Path(pasta)
    arquivo_manifesto = pasta / "manifesto.json"

    if not arquivo_manifesto.exists():
        print(f"[ERRO] manifesto.json não encontrado em {pasta}")
        return 2

    manifesto = mod_manifesto.carregar(arquivo_manifesto)

    print("=" * 60)
    print(" VERIFICAÇÃO DE INTEGRIDADE — ProvaSocial-Extract")
    print("=" * 60)
    print(f" Coleta...........: {manifesto.get('coleta_id')}")
    print(f" Código...........: {manifesto.get('codigo_verificacao')}")
    print(f" URL alvo.........: {manifesto.get('url_alvo')}")
    print(f" Coletado em......: {manifesto.get('gerado_em', {}).get('brasilia')}")
    print("-" * 60)

    ok_manifesto, problemas_manifesto = mod_manifesto.verificar(manifesto, pasta)

    arquivo_cadeia = pasta / "cadeia_custodia.json"
    ok_cadeia, problemas_cadeia = True, []
    if arquivo_cadeia.exists():
        import json

        cadeia = json.loads(arquivo_cadeia.read_text(encoding="utf-8"))
        ok_cadeia, problemas_cadeia = CadeiaCustodia.verificar(cadeia)

    todos_problemas = problemas_manifesto + problemas_cadeia

    if ok_manifesto and ok_cadeia:
        print(" RESULTADO: ÍNTEGRO ✓")
        print(" Todos os artefatos conferem com os hashes registrados.")
        print(" A cadeia de custódia está encadeada corretamente.")
        print("=" * 60)
        return 0

    print(" RESULTADO: ADULTERADO ✗")
    print(f" {len(todos_problemas)} problema(s) encontrado(s):")
    for p in todos_problemas:
        print(f"   - {p}")
    print("=" * 60)
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Uso: python verificar.py <pasta_da_coleta>")
        return 2
    return verificar_pasta(argv[0])


if __name__ == "__main__":
    raise SystemExit(main())
