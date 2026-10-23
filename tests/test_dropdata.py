import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication
from fotolista.dropdata import drop_payload

APP = QApplication.instance() or QApplication([])


class DropDataTests(unittest.TestCase):
    def test_browser_text_url_and_firefox_and_windows_url(self):
        for fmt in ("text/plain", "text/x-moz-url", 'application/x-qt-windows-mime;value="UniformResourceLocatorW"'):
            with self.subTest(fmt=fmt):
                mime = QMimeData()
                if fmt == "text/plain":
                    mime.setText("https://example.com/foto.png\nTítulo")
                else:
                    mime.setData(fmt, "https://example.com/foto.png\x00".encode("utf-16-le"))
                self.assertEqual(drop_payload(mime), ([], ["https://example.com/foto.png"]))

    def test_file_url_and_plain_file_path(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "foto con espacios.png"
            path.write_bytes(b"placeholder")
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            local, sources = drop_payload(mime)
            self.assertEqual([Path(p) for p in local], [path])
            self.assertEqual(sources, [])
            mime = QMimeData()
            mime.setText(str(path))
            local, sources = drop_payload(mime)
            self.assertEqual([Path(p) for p in local], [path])
            self.assertEqual(sources, [])

    def test_windows_virtual_file_and_binary_image(self):
        stream = BytesIO()
        Image.new("RGB", (30, 20), "red").save(stream, format="PNG")
        for fmt in ('application/x-qt-windows-mime;value="FileContents";index=0', 'image/png'):
            mime = QMimeData()
            mime.setData(fmt, stream.getvalue())
            self.assertEqual(drop_payload(mime), ([], [stream.getvalue()]))

    def test_unsupported_payload(self):
        mime = QMimeData()
        mime.setText("Texto sin imagen")
        self.assertEqual(drop_payload(mime), ([], []))
