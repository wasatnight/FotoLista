import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
import random
from unittest.mock import patch
from PIL import Image
from fotolista.processing import Cancelled, Settings, inspect, prepare
from fotolista.exporting import export_one, safe_prefix


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photo = self.root / "casa.jpg"
        Image.effect_noise((1600, 1000), 90).convert("RGB").save(self.photo, quality=98)

    def tearDown(self):
        self.temp.cleanup()

    def test_limits_for_every_format(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                result = prepare(self.photo, Settings(format=fmt, limit=20_000))
                self.assertLessEqual(len(result.data), 20_000)
                self.assertLessEqual(result.width, 1600)
                self.assertAlmostEqual(result.width / result.height, 1.6, delta=0.03)
                with Image.open(BytesIO(result.data)) as out:
                    out.load()
                    self.assertEqual(out.size, (result.width, result.height))

    def test_high_detail_color_jpeg_encoder(self):
        path = self.root / "detalle.png"
        Image.frombytes("RGB", (700, 500), random.Random(42).randbytes(700 * 500 * 3)).save(path)
        result = prepare(path, Settings(limit=100_000))
        self.assertLessEqual(len(result.data), 100_000)
        with Image.open(BytesIO(result.data)) as out:
            out.verify()

    def test_no_enlarge_or_recompress_when_already_fits(self):
        for fmt, ext in (("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")):
            path = self.root / ("small" + ext)
            Image.new("RGB", (80, 50), "red").save(path, format=fmt)
            result = prepare(path, Settings(format=fmt, pixels=2000))
            self.assertEqual((result.width, result.height), (80, 50))
            self.assertLessEqual(len(result.data), path.stat().st_size)

    def test_resize_and_orientation_and_privacy(self):
        path = self.root / "orientada.jpg"
        exif = Image.Exif()
        exif[274], exif[315] = 6, "Autor privado"
        Image.new("RGB", (120, 80), "blue").save(path, exif=exif)
        result = prepare(path, Settings(pixels=60, resize_mode="width"))
        with Image.open(BytesIO(result.data)) as out:
            self.assertEqual(out.size, (60, 90))
            self.assertFalse(out.getexif())
        result = prepare(path, Settings(strip_metadata=False))
        with Image.open(BytesIO(result.data)) as out:
            self.assertEqual(out.size, (80, 120))
            self.assertEqual(out.getexif()[315], "Autor privado")
            self.assertNotIn(274, out.getexif())

    def test_metadata_removal_without_recompression(self):
        for fmt, ext in (("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")):
            path = self.root / ("private" + ext)
            exif = Image.Exif()
            exif[315] = "Privado"
            Image.new("RGB", (100, 70), "blue").save(path, format=fmt, exif=exif)
            result = prepare(path, Settings(format=fmt))
            with Image.open(BytesIO(result.data)) as out, Image.open(path) as original:
                self.assertFalse(out.getexif())
                self.assertEqual(out.tobytes(), original.tobytes())

    def test_transparency(self):
        path = self.root / "alpha.png"
        Image.new("RGBA", (40, 40), (255, 0, 0, 0)).save(path)
        for bg, rgb in (("#ffffff", (255, 255, 255)), ("#00ff00", (0, 255, 0))):
            result = prepare(path, Settings(background=bg))
            with Image.open(BytesIO(result.data)) as out:
                self.assertTrue(all(abs(a-b) < 4 for a, b in zip(out.getpixel((20, 20)), rgb)))

    def test_duplicates_and_original_hash(self):
        before = hashlib.sha256(self.photo.read_bytes()).hexdigest()
        one, _ = export_one(self.photo, self.root, Settings(), 1)
        two, _ = export_one(self.photo, self.root, Settings(), 2)
        self.assertNotEqual(one, two)
        self.assertNotEqual(one, self.photo)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(), before)
        renamed, _ = export_one(self.photo, self.root, Settings(prefix="Casa_Rialto"), 1)
        self.assertEqual(renamed.name, "Casa_Rialto_01.jpg")

    def test_cancel_before_and_during_write(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            export_one(self.photo, self.root, Settings(), 1, cancel)
        cancel.clear()
        def stop(_):
            cancel.set()
        with patch("fotolista.exporting.os.fsync", side_effect=stop):
            with self.assertRaises(Cancelled):
                export_one(self.photo, self.root, Settings(), 1, cancel)
        self.assertEqual(list(self.root.glob(".fotolista-*")), [])
        self.assertEqual(list(self.root.glob("casa (*")), [])

    def test_invalid_and_impossible(self):
        bad = self.root / "rota.jpg"
        bad.write_text("No es una imagen")
        with self.assertRaises(Exception):
            inspect(bad)
        with self.assertRaises(ValueError):
            prepare(self.photo, Settings(limit=1))
        self.assertEqual(safe_prefix("CON"), "Foto_CON")

    def test_heif_roundtrip(self):
        from pillow_heif import from_pillow
        path = self.root / "movil.heic"
        from_pillow(Image.new("RGB", (120, 80), "green")).save(path)
        self.assertEqual(inspect(path)[1], (120, 80))
        result = prepare(path, Settings())
        self.assertEqual(result.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
