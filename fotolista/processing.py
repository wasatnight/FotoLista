"""Motor independiente de Qt. Un archivo a resolución completa por tarea."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Event
import math
import struct

from PIL import Image, ImageColor, ImageOps, ImageFile

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

SUPPORTED = {"JPEG", "PNG", "WEBP"} | ({"HEIF", "HEIC"} if HEIF_AVAILABLE else set())


class Cancelled(Exception):
    pass


def checkpoint(cancel):
    if cancel and cancel.is_set():
        raise Cancelled("Operación cancelada")


@dataclass(frozen=True)
class Settings:
    format: str = "JPEG"
    limit: int | None = 5_000_000
    resize_mode: str = "longest"
    pixels: int | None = None
    strip_metadata: bool = True
    background: str = "#ffffff"
    prefix: str | None = None


@dataclass
class Prepared:
    data: bytes
    width: int
    height: int
    format: str
    quality: int | None
    copied: bool = False


def without_personal_metadata(data, fmt):
    """Quita metadatos sin recomprimir los píxeles en los tres formatos."""
    if fmt == "JPEG":
        out, pos = bytearray(data[:2]), 2
        while pos < len(data):
            start = pos
            if data[pos] != 255:
                raise ValueError("Estructura JPEG no válida")
            while data[pos] == 255:
                pos += 1
            marker = data[pos]
            pos += 1
            if marker in (0xDA, 0xD9):
                out.extend(data[start:])
                break
            length = int.from_bytes(data[pos:pos + 2], "big")
            end = pos + length
            if length < 2 or end > len(data):
                raise ValueError("Segmento JPEG no válido")
            if marker not in {*range(0xE1, 0xF0), 0xFE} or marker in (0xE2, 0xEE):
                out.extend(data[start:end])
            pos = end
        return bytes(out)
    if fmt == "PNG":
        out, pos = bytearray(data[:8]), 8
        keep = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"iCCP", b"sRGB", b"gAMA", b"cHRM", b"sBIT", b"pHYs"}
        while pos + 12 <= len(data):
            length = int.from_bytes(data[pos:pos + 4], "big")
            end = pos + length + 12
            if end > len(data):
                raise ValueError("Estructura PNG no válida")
            if data[pos + 4:pos + 8] in keep:
                out.extend(data[pos:end])
            pos = end
        return bytes(out)
    if fmt == "WEBP":
        chunks, pos = bytearray(b"WEBP"), 12
        while pos + 8 <= len(data):
            kind = data[pos:pos + 4]
            length = int.from_bytes(data[pos + 4:pos + 8], "little")
            end = pos + 8 + length + length % 2
            chunk = bytearray(data[pos:end])
            if kind == b"VP8X":
                chunk[8] &= ~(0x08 | 0x04)
            if kind not in (b"EXIF", b"XMP "):
                chunks.extend(chunk)
            pos = end
        return b"RIFF" + struct.pack("<I", len(chunks)) + bytes(chunks)
    return data


def inspect(path):
    with Image.open(path) as src:
        if src.format not in SUPPORTED:
            raise ValueError("Formato no compatible. Usa JPG, PNG, WebP o HEIC/HEIF compatible.")
        if getattr(src, "n_frames", 1) > 1:
            raise ValueError("Las imágenes animadas o con varias páginas no se admiten en esta versión.")
        fmt = src.format
        image = ImageOps.exif_transpose(src)
        image.load()
        thumb = image.copy()
        thumb.thumbnail((180, 130))
        return fmt, image.size, Path(path).stat().st_size, thumb


def prepare(path: Path, settings: Settings, cancel: Event | None = None) -> Prepared:
    checkpoint(cancel)
    if settings.format not in {"JPEG", "PNG", "WEBP"}:
        raise ValueError("Formato de salida no compatible")
    if settings.limit is not None and settings.limit < 1:
        raise ValueError("El límite debe ser mayor que cero")
    if settings.pixels is not None and settings.pixels < 1:
        raise ValueError("Las dimensiones deben ser mayores que cero")
    with Image.open(path) as src:
        if src.format not in SUPPORTED or getattr(src, "n_frames", 1) > 1:
            raise ValueError("Formato no compatible o imagen de varias páginas")
        original_format = src.format
        orientation = src.getexif().get(274, 1)
        im = ImageOps.exif_transpose(src)
        im.load()
        checkpoint(cancel)
        # EXIF ya corregido; conservarlo es una elección explícita del usuario.
        metadata = {}
        if not settings.strip_metadata:
            exif = im.getexif()
            if exif:
                metadata["exif"] = exif.tobytes()
        # El perfil de color no contiene GPS y evita cambios de color inesperados.
        if im.info.get("icc_profile"):
            metadata["icc_profile"] = im.info["icc_profile"]
        denominator = im.width if settings.resize_mode == "width" else max(im.size)
        scale = min(1, settings.pixels / denominator) if settings.pixels else 1
        if scale < 1:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
        # Si ya cumple, conservar los píxeles; eliminar metadatos sin recomprimir.
        if (orientation == 1 and scale == 1
                and original_format == settings.format
                and (settings.limit is None or path.stat().st_size <= settings.limit)):
            data = path.read_bytes()
            if settings.strip_metadata:
                data = without_personal_metadata(data, original_format)
            return Prepared(data, *im.size, settings.format, None, True)
        if settings.format == "JPEG":
            if "A" in im.getbands() or "transparency" in im.info:
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", im.size, ImageColor.getrgb(settings.background))
                bg.paste(rgba, mask=rgba.getchannel("A"))
                im = bg
            else:
                im = im.convert("RGB")
        elif im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "transparency" in im.info else "RGB")

        def encode(quality):
            checkpoint(cancel)
            buffer = BytesIO()
            kwargs = dict(metadata)
            if settings.format == "PNG":
                kwargs.update(optimize=True, compress_level=9)
            elif settings.format == "JPEG":
                kwargs.update(quality=quality, optimize=True, progressive=True, subsampling=0)
            else:
                kwargs.update(quality=quality, method=6)
            # JPEG 4:4:4 con ruido puede superar la estimación interna de Pillow.
            # El motor se ejecuta secuencialmente; restaurar el búfer tras cada guardado.
            previous_block = ImageFile.MAXBLOCK
            try:
                if settings.format == "JPEG":
                    ImageFile.MAXBLOCK = max(previous_block, im.width * im.height * 4 + 65536)
                im.save(buffer, format=settings.format, **kwargs)
            finally:
                ImageFile.MAXBLOCK = previous_block
            checkpoint(cancel)
            return buffer.getvalue()

        while True:
            # Busca la calidad más alta que cabe, sin bajar de 45 antes de redimensionar.
            quality = None if settings.format == "PNG" else 95
            data = encode(quality)
            if settings.limit is None or len(data) <= settings.limit:
                return Prepared(data, *im.size, settings.format, quality)
            if quality is not None:
                low, high, best = 45, 94, None
                while low <= high:
                    mid = (low + high) // 2
                    candidate = encode(mid)
                    if len(candidate) <= settings.limit:
                        best = (candidate, mid)
                        low = mid + 1
                    else:
                        high = mid - 1
                if best:
                    return Prepared(best[0], *im.size, settings.format, best[1])
                data = encode(45)
            if im.size == (1, 1):
                raise ValueError("El límite es menor que el mínimo del formato y sus metadatos. Aumenta el límite, elimina metadatos o elige JPG/WebP.")
            ratio = min(0.85, max(0.1, math.sqrt(settings.limit / len(data)) * 0.93))
            size = (max(1, int(im.width * ratio)), max(1, int(im.height * ratio)))
            im = im.resize(size, Image.Resampling.LANCZOS)
            checkpoint(cancel)
