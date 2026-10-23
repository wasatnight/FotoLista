"""Importación de imágenes arrastradas desde navegadores, sin abrir páginas HTML."""
import base64
from html.parser import HTMLParser
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
from .processing import checkpoint, inspect

MAX_DOWNLOAD = 60_000_000


class ImageSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            src = dict(attrs).get("src", "")
            if src.startswith(("https://", "http://", "data:image/")):
                self.urls.append(src)


def browser_sources(html, urls):
    parser = ImageSources()
    parser.feed(html or "")
    # Un enlace arrastrado puede apuntar a la página; el <img> identifica la foto.
    sources = parser.urls or urls
    return list(dict.fromkeys(src for src in sources if src.startswith(("https://", "http://", "data:image/"))))


def import_image(source, directory, cancel=None):
    checkpoint(cancel)
    name = "Imagen_navegador"
    fd, temp = tempfile.mkstemp(prefix="descarga-", dir=directory)
    import os
    try:
        with os.fdopen(fd, "wb") as stream:
            if isinstance(source, bytes):
                if len(source) > MAX_DOWNLOAD:
                    raise ValueError("La imagen supera 60 MB. Guárdala y añádela como archivo.")
                stream.write(source)
            elif source.startswith("data:image/"):
                if len(source) > MAX_DOWNLOAD * 1.4:
                    raise ValueError("La imagen incrustada supera 60 MB")
                header, payload = source.split(",", 1)
                from urllib.parse import unquote_to_bytes
                data = base64.b64decode(payload, validate=True) if ";base64" in header else unquote_to_bytes(payload)
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError("La imagen incrustada supera 60 MB")
                stream.write(data)
            else:
                if urlsplit(source).scheme not in ("http", "https"):
                    raise ValueError("Arrastra una imagen o un enlace directo HTTP/HTTPS")
                name = unquote(Path(urlsplit(source).path).stem) or name
                request = Request(source, headers={"User-Agent": "FotoLista/1.0"})
                with urlopen(request, timeout=15) as response:
                    if urlsplit(response.geturl()).scheme not in ("http", "https"):
                        raise ValueError("La dirección de imagen no es compatible")
                    total = 0
                    while True:
                        checkpoint(cancel)
                        block = response.read(65536)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_DOWNLOAD:
                            raise ValueError("La descarga supera 60 MB. Guarda la imagen y añádela como archivo.")
                        stream.write(block)
        checkpoint(cancel)
        fmt, *_ = inspect(temp)
        ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "HEIF": ".heic", "HEIC": ".heic"}[fmt]
        name = re.sub(r'[^\w .-]', "_", name).strip(". ")[:80] or "Imagen_navegador"
        # Directorio privado por importación para conservar nombres sin colisiones.
        folder = Path(tempfile.mkdtemp(prefix="imagen-", dir=directory))
        target = folder / ("Web_" + name + ext)
        Path(temp).rename(target)
        return str(target)
    finally:
        Path(temp).unlink(missing_ok=True)
