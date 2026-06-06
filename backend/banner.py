"""Banner ASCII exibido na inicializacao do sistema."""

from __future__ import annotations

BANNER = r"""
   ____                  ____          _            _ _
  / ___|  ___ _   _     / ___|   _ ___| |_ ___   __| (_) ___
  \___ \ / _ \ | | |   | |  | | | / __| __/ _ \ / _` | |/ _ \
   ___) |  __/ |_| |   | |__| |_| \__ \ || (_) | (_| | | (_) |
  |____/ \___|\__,_|    \____\__,_|___/\__\___/ \__,_|_|\___/

               Guarda . Confere . Preserva
               Code by Cyber_Marmouts
               Site: www.cybermarmouts.com.br
"""


def imprimir_banner() -> None:
    """Imprime o banner no terminal."""
    print(BANNER)
