import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from PIL import Image
from fotolista.importing import browser_sources, import_image
from fotolista.processing import Cancelled, inspect


class FakeResponse(BytesIO):
    def geturl(self):
        return "https://images.example/foto.png"


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        data = BytesIO()
        Image.new("RGB", (90, 60), "green").save(data, format="PNG")
        self.png = data.getvalue()

    def tearDown(self):
        self.temp.cleanup()

    def test_image_html_preferred_over_page_link(self):
        sources = browser_sources('<a href="https://site.example/page"><img src="https://images.example/foto.png"></a>', ["https://site.example/page"])
        self.assertEqual(sources, ["https://images.example/foto.png"])
        self.assertEqual(browser_sources("", ["file:///c:/foto.jpg", "javascript:bad"]), [])

    def test_embedded_and_pixels_and_duplicate_names(self):
        url = "data:image/png;base64," + base64.b64encode(self.png).decode()
        one = import_image(url, self.root)
        two = import_image(self.png, self.root)
        self.assertNotEqual(one, two)
        self.assertEqual(inspect(one)[1], (90, 60))
        self.assertEqual(Path(two).read_bytes(), self.png)

    def test_remote_download_and_invalid_response(self):
        with patch("fotolista.importing.urlopen", return_value=FakeResponse(self.png)):
            path = import_image("https://images.example/casa.png", self.root)
        self.assertEqual(Path(path).name, "Web_casa.png")
        self.assertEqual(inspect(path)[1], (90, 60))
        with patch("fotolista.importing.urlopen", return_value=FakeResponse(b"<html>No es una imagen</html>")):
            with self.assertRaises(Exception):
                import_image("https://site.example/page", self.root)
        self.assertEqual(list(self.root.glob("descarga-*")), [])

    def test_size_and_cancellation_and_scheme(self):
        with patch("fotolista.importing.MAX_DOWNLOAD", 10):
            with self.assertRaises(ValueError):
                import_image(self.png, self.root)
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            import_image(self.png, self.root, cancel)
        with self.assertRaises(ValueError):
            import_image("file:///c:/private", self.root)
        self.assertEqual(list(self.root.iterdir()), [])
