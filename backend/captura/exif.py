"""Análise forense de metadados de mídia (EXIF/XMP/GPS).

Estratégia em camadas:
  1. ExifTool (se instalado no sistema) — extração mais completa e confiável.
  2. Fallback Pillow — EXIF básico + GPS para imagens, sem dependências externas.

Sempre retorna ao menos os dados básicos do arquivo (tamanho, tipo).
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
from pathlib import Path


def exiftool_disponivel() -> bool:
    return shutil.which("exiftool") is not None


def analisar_midia(caminho: str | Path) -> dict:
    """Extrai metadados de um arquivo de mídia.

    Retorna dict com: arquivo, tamanho, mime, fonte (exiftool|pillow|nenhum),
    metadados (dict) e, quando houver, gps (dict com latitude/longitude).
    """
    caminho = Path(caminho)
    info: dict = {
        "arquivo": caminho.name,
        "tamanho": caminho.stat().st_size if caminho.exists() else 0,
        "mime": mimetypes.guess_type(str(caminho))[0],
        "fonte": "nenhum",
        "metadados": {},
        "gps": None,
    }
    if not caminho.exists():
        return info

    if exiftool_disponivel():
        dados = _via_exiftool(caminho)
        if dados:
            info["fonte"] = "exiftool"
            info["metadados"] = dados
            info["gps"] = _gps_de_exiftool(dados)
            return info

    # Fallback: Pillow (apenas imagens)
    dados, gps = _via_pillow(caminho)
    if dados:
        info["fonte"] = "pillow"
        info["metadados"] = dados
        info["gps"] = gps
    return info


# --------------------------------------------------------------------------- #
# ExifTool                                                                     #
# --------------------------------------------------------------------------- #
def _via_exiftool(caminho: Path) -> dict | None:
    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-n", "-a", "-u", str(caminho)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            dados = json.loads(proc.stdout)
            if isinstance(dados, list) and dados:
                d = dict(dados[0])
                d.pop("SourceFile", None)
                return d
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        pass
    return None


def _gps_de_exiftool(dados: dict) -> dict | None:
    lat = dados.get("GPSLatitude")
    lon = dados.get("GPSLongitude")
    if lat is not None and lon is not None:
        return {"latitude": lat, "longitude": lon}
    return None


# --------------------------------------------------------------------------- #
# Fallback Pillow                                                              #
# --------------------------------------------------------------------------- #
def _via_pillow(caminho: Path) -> tuple[dict | None, dict | None]:
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return None, None

    try:
        with Image.open(caminho) as img:
            exif = img.getexif()
            if not exif:
                return {"formato": img.format, "dimensoes": list(img.size)}, None

            legivel: dict = {"formato": img.format, "dimensoes": list(img.size)}
            for tag_id, valor in exif.items():
                nome = ExifTags.TAGS.get(tag_id, str(tag_id))
                legivel[nome] = _serializavel(valor)

            gps = _gps_pillow(exif, ExifTags)
            return legivel, gps
    except Exception:  # noqa: BLE001 — arquivo não-imagem ou corrompido
        return None, None


def _gps_pillow(exif, ExifTags) -> dict | None:
    try:
        gps_ifd = exif.get_ifd(0x8825)  # GPSInfo
    except Exception:  # noqa: BLE001
        gps_ifd = None
    if not gps_ifd:
        return None

    nomeado = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
    lat = _coord_para_graus(nomeado.get("GPSLatitude"), nomeado.get("GPSLatitudeRef"))
    lon = _coord_para_graus(nomeado.get("GPSLongitude"), nomeado.get("GPSLongitudeRef"))
    if lat is None or lon is None:
        return None
    return {"latitude": lat, "longitude": lon}


def _coord_para_graus(coord, ref) -> float | None:
    """Converte (graus, minutos, segundos) + referência (N/S/E/W) em graus decimais."""
    if not coord or len(coord) != 3:
        return None
    try:
        graus = float(coord[0]) + float(coord[1]) / 60.0 + float(coord[2]) / 3600.0
        if ref in ("S", "W"):
            graus = -graus
        return round(graus, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _serializavel(valor):
    """Garante que o valor possa ir para JSON."""
    if isinstance(valor, bytes):
        return valor.hex()[:128]
    if isinstance(valor, (list, tuple)):
        return [_serializavel(v) for v in valor]
    try:
        json_ok = (int, float, str, bool, type(None))
        if isinstance(valor, json_ok):
            return valor
        return str(valor)
    except Exception:  # noqa: BLE001
        return str(valor)
