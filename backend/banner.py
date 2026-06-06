"""Banner ASCII exibido na inicializacao do sistema."""

from __future__ import annotations

BANNER = r"""
  ____      _                __  __                              _
 / ___|   _| |__   ___ _ __ |  \/  | __ _ _ __ _ __ ___   ___  _   _| |_ ___
| |  | | | | '_ \ / _ \ '__|| |\/| |/ _` | '__| '_ ` _ \ / _ \| | | | __/ __|
| |__| |_| | |_) |  __/ |   | |  | | (_| | |  | | | | | | (_) | |_| | |_\__ \
 \____\__, |_.__/ \___|_|   |_|  |_|\__,_|_|  |_| |_| |_|\___/ \__,_|\__|___/
      |___/

               ProvaSocial Extract - Coleta Forense Auditavel
               Autor: @cyber_marmouts
               Site : www.cybermarmouts.com.br
"""


def imprimir_banner() -> None:
    """Imprime o banner no terminal."""
    print(BANNER)
