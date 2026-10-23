import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage
from PySide6.QtWidgets import QApplication
from fotolista.workers import Task
from fotolista.processing import Settings
from fotolista.ui import Window

APP = QApplication.instance() or QApplication([])


class WorkerTests(unittest.TestCase):
    def test_full_drag_sequence_on_header_list_and_window(self):
        with TemporaryDirectory() as directory:
            photo = Path(directory) / "foto.png"
            Image.new("RGB", (80, 60), "blue").save(photo)
            from PySide6.QtCore import QUrl
            for zone in ("header", "list", "window"):
                with self.subTest(zone=zone):
                    window = Window()
                    surface = {"header": window.drop, "list": window.files.viewport(), "window": window}[zone]
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(str(photo))])
                    actions = Qt.CopyAction | Qt.MoveAction | Qt.LinkAction
                    enter = QDragEnterEvent(QPoint(10, 10), actions, mime, Qt.LeftButton, Qt.NoModifier)
                    APP.sendEvent(surface, enter)
                    self.assertTrue(enter.isAccepted())
                    move = QDragMoveEvent(QPoint(10, 10), actions, mime, Qt.LeftButton, Qt.NoModifier)
                    APP.sendEvent(surface, move)
                    self.assertTrue(move.isAccepted())
                    self.assertTrue(window.drop.property("dragActive"))
                    self.assertEqual(move.dropAction(), Qt.CopyAction)
                    drop = QDropEvent(QPointF(10, 10), actions, mime, Qt.LeftButton, Qt.NoModifier)
                    APP.sendEvent(surface, drop)
                    self.assertTrue(drop.isAccepted())
                    self.assertEqual(drop.dropAction(), Qt.CopyAction)
                    loop = QEventLoop()
                    window.task.finished.connect(loop.quit)
                    loop.exec()
                    APP.processEvents()
                    self.assertEqual(window.files.count(), 1)
                    self.assertFalse(window.drop.property("dragActive"))
                    self.assertTrue(photo.exists())
                    window.close()

    def test_browser_pixels_drop_on_file_list(self):
        window = Window()
        mime = QMimeData()
        image = QImage(80, 60, QImage.Format_RGB32)
        image.fill(Qt.green)
        mime.setImageData(image)
        enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        APP.sendEvent(window.files.viewport(), enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        APP.sendEvent(window.files.viewport(), drop)
        self.assertTrue(drop.isAccepted())
        loop = QEventLoop()
        window.task.finished.connect(loop.quit)
        loop.exec()
        APP.processEvents()
        self.assertEqual(window.files.count(), 1)
        path = next(iter(window.records))
        self.assertTrue(Path(path).exists())
        window.close()
        self.assertFalse(Path(path).exists())

    def run_task(self, task, on_item=None):
        items, errors, outcomes = [], [], []
        loop = QEventLoop()
        task.item.connect(items.append)
        if on_item:
            task.item.connect(on_item)
        task.failed.connect(errors.append)
        task.outcome.connect(outcomes.append)
        task.finished.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(task.cancel.set)
        timer.start(30000)
        task.start()
        loop.exec()
        task.wait()
        return items, errors, outcomes

    def test_batch_continues_after_failure_and_preview(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "foto.png"
            Image.new("RGB", (400, 300), "red").save(good)
            bad = root / "rota.png"
            bad.write_bytes(b"incorrecto")
            items, errors, outcomes = self.run_task(Task("export", [str(bad), str(good)], Settings(), root))
            self.assertEqual(len(items), 1)
            self.assertEqual(len(errors), 1)
            self.assertEqual(outcomes, [False])
            items, errors, _ = self.run_task(Task("preview", [str(good)], Settings()))
            self.assertEqual(errors, [])
            self.assertEqual(items[0][1].preview_before.size, (400, 300))

    def test_batch_cancellation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "foto.png"
            Image.new("RGB", (50, 40), "red").save(good)
            task = Task("export", [str(good)] * 1000, Settings(), root)
            items, errors, outcomes = self.run_task(task, lambda _: task.cancel.set())
            self.assertEqual(outcomes, [True])
            self.assertLess(len(items), 1000)
            self.assertEqual(errors, [])
            for path in root.glob("*.jpg"):
                with Image.open(path) as im:
                    im.verify()
            self.assertEqual(list(root.glob(".fotolista-*")), [])

    def test_window_load_preview_export(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            photo = root / "casa.png"
            Image.new("RGB", (600, 400), "#438574").save(photo)
            window = Window()
            def wait():
                loop = QEventLoop()
                window.task.finished.connect(loop.quit)
                loop.exec()
                APP.processEvents()
            window.load_paths([str(photo)])
            wait()
            self.assertEqual(window.files.count(), 1)
            window.make_preview()
            wait()
            self.assertIsNotNone(window.comparison.after)
            window.destination = directory
            window.export_all()
            wait()
            self.assertEqual(window.exported, 1)
            self.assertTrue((root / "casa.jpg").exists())
            # Quitar la última foto debe limpiar tanto la vista como el estado del lote.
            window.files.selectAll()
            window.slider.setValue(0)
            window.remove_selected()
            self.assertEqual(window.files.count(), 0)
            self.assertEqual(window.records, {})
            self.assertEqual(window.count.text(), "0 fotografías")
            self.assertEqual(window.progress.value(), 0)
            self.assertIsNone(window.comparison.before)
            self.assertIsNone(window.comparison.after)
            self.assertEqual(window.slider.value(), 50)
            self.assertIn("No hay fotografías", window.status.text())
            self.assertTrue(photo.exists())
            self.assertTrue((root / "casa.jpg").exists())
            window.close()


if __name__ == "__main__":
    unittest.main()
