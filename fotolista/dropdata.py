"""Normaliza formatos de arrastre de navegadores y del Explorador de Windows."""
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QImage, QPixmap
from .importing import browser_sources, MAX_DOWNLOAD


def drop_payload(mime):
    urls = list(mime.urls())
    # Algunos navegadores entregan la dirección como texto, no como text/uri-list.
    candidates = [mime.text()] if mime.hasText() else []
    for fmt in mime.formats():
        if fmt == "text/x-moz-url" or "UniformResourceLocator" in fmt:
            raw = bytes(mime.data(fmt))
            encoding = "utf-16-le" if "LocatorW" in fmt or fmt == "text/x-moz-url" else "utf-8"
            candidates.append(raw.decode(encoding, errors="replace").strip("\x00"))
    for candidate in candidates:
        for line in candidate.splitlines():
            value = line.strip().strip('"').strip("\x00")
            if value.startswith(("http://", "https://", "file://", "data:image/")):
                urls.append(QUrl(value))
            elif value and Path(value).is_absolute() and Path(value).is_file():
                urls.append(QUrl.fromLocalFile(value))
    local = list(dict.fromkeys(url.toLocalFile() for url in urls if url.isLocalFile()))
    if local:
        return local, []
    # Preferir píxeles que ya comparte el navegador antes de solicitar otra descarga.
    if mime.hasImage():
        image = mime.imageData()
        if isinstance(image, QPixmap):
            image = image.toImage()
        if isinstance(image, QImage) and not image.isNull():
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            if image.save(buffer, "PNG"):
                data = bytes(buffer.data())
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError("La imagen supera 60 MB. Guárdala y añádela como archivo.")
                return [], [data]
    binary = []
    for fmt in mime.formats():
        if fmt.startswith("image/") or 'value="FileContents"' in fmt:
            data = bytes(mime.data(fmt))
            if len(data) > MAX_DOWNLOAD:
                raise ValueError("La imagen supera 60 MB. Guárdala y añádela como archivo.")
            if data and data not in binary:
                binary.append(data)
    if binary:
        return [], binary
    return [], browser_sources(mime.html(), [url.toString() for url in urls])
