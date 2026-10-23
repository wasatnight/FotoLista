from pathlib import Path
from threading import Event
from io import BytesIO
from PIL import Image, ImageOps
from PySide6.QtCore import QThread, Signal
from .processing import Cancelled, inspect, prepare
from .exporting import export_one
from .importing import import_image


class Task(QThread):
    item = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    outcome = Signal(bool)

    def __init__(self, mode, paths, settings=None, destination=None):
        super().__init__()
        self.mode, self.paths = mode, paths
        self.settings, self.destination = settings, destination
        self.cancel = Event()

    def run(self):
        stopped = False
        for i, path in enumerate(self.paths, 1):
            if self.cancel.is_set():
                stopped = True
                break
            try:
                if self.mode == "load":
                    self.item.emit((path, *inspect(path)))
                elif self.mode == "import":
                    imported = import_image(path, self.destination, self.cancel)
                    self.item.emit((imported, *inspect(imported)))
                elif self.mode == "preview":
                    result = prepare(Path(path), self.settings, self.cancel)
                    with Image.open(path) as source:
                        before = ImageOps.exif_transpose(source)
                        before.thumbnail((1500, 1000))
                        result.preview_before = before.convert("RGBA")
                    with Image.open(BytesIO(result.data)) as source:
                        source.thumbnail((1500, 1000))
                        result.preview_after = source.convert("RGBA")
                    self.item.emit((path, result))
                else:
                    target, result = export_one(path, self.destination, self.settings, i, self.cancel)
                    self.item.emit((path, target, result))
            except Cancelled:
                stopped = True
                break
            except Exception as exc:
                label = "Imagen del navegador" if self.mode == "import" else Path(path).name
                advice = ". Si el sitio impide importar, guarda la imagen y añádela como archivo." if self.mode == "import" else ""
                self.failed.emit(f"{label}: {exc}{advice}")
            self.progress.emit(i, len(self.paths))
        self.outcome.emit(stopped or self.cancel.is_set())
