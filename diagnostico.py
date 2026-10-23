"""Comprobación reproducible del paquete con datos sintéticos, sin red."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from PySide6.QtWidgets import QApplication
from fotolista.processing import Settings, inspect
from fotolista.exporting import export_one
from fotolista.ui import Window


def run(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    checks = []
    with TemporaryDirectory(dir=destination) as tmp:
        root = Path(tmp)
        image = Image.new("RGBA", (640, 480), (45, 160, 135, 140))
        source = root / "prueba.png"
        image.save(source)
        for fmt in ("JPEG", "PNG", "WEBP"):
            target, result = export_one(source, root, Settings(format=fmt, limit=20_000), 1)
            with Image.open(target) as saved:
                saved.verify()
            checks.append({"formato": fmt, "bytes": len(result.data), "limite": 20_000})
        from pillow_heif import from_pillow
        heic = root / "prueba.heic"
        from_pillow(image.convert("RGB")).save(heic)
        inspect(heic)
        checks.append({"HEIC": "lectura correcta"})
        window = Window()
        window.show()
        app.processEvents()
        window.loaded((str(source), *inspect(source)))
        app.processEvents()
        window.grab().save(str(destination / "interfaz.png"))
        window.close()
    (destination / "diagnostico.json").write_text(json.dumps({"estado": "OK", "comprobaciones": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
