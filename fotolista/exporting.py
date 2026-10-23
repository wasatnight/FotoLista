"""Publicación de temporales completos sin sobrescribir archivos existentes."""
import os
import re
import tempfile
from pathlib import Path
from .processing import checkpoint, prepare

EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def safe_prefix(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
    if not value:
        raise ValueError("Escribe un prefijo válido para los nombres")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "Foto_" + value
    return value[:120]


def export_one(source, destination, settings, index, cancel=None):
    source, destination = Path(source), Path(destination)
    result = prepare(source, settings, cancel)
    checkpoint(cancel)
    if settings.limit and len(result.data) > settings.limit:
        raise ValueError("El archivo generado excede el límite")
    stem = f"{safe_prefix(settings.prefix)}_{index:02d}" if settings.prefix else source.stem
    # Nunca usar un nombre que sobrescriba, incluso al elegir la carpeta original.
    fd, tmp = tempfile.mkstemp(prefix=".fotolista-", suffix=".tmp", dir=destination)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(result.data)
            stream.flush()
            os.fsync(stream.fileno())
        if Path(tmp).stat().st_size != len(result.data):
            raise OSError("No se pudo verificar el archivo escrito")
        checkpoint(cancel)
        suffix = 0
        while True:
            name = stem + (f" ({suffix})" if suffix else "") + EXTENSIONS[result.format]
            target = destination / name
            try:
                # Windows: rename es atómico y falla si el destino ya existe.
                # POSIX: link proporciona la misma exclusión sin replace.
                if os.name == "nt":
                    os.rename(tmp, target)
                else:
                    os.link(tmp, target)
                break
            except FileExistsError:
                suffix += 1
            except OSError as exc:
                raise OSError(f"No se pudo guardar la copia en {destination}: {exc}") from exc
        return target, result
    finally:
        Path(tmp).unlink(missing_ok=True)
