import os
import sys
from tempfile import TemporaryDirectory
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QRectF, QUrl, QSize, QEvent
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap, QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSlider, QSpinBox, QSplitter, QVBoxLayout, QWidget, QScrollArea, QLayout)
from PySide6.QtWidgets import QAbstractItemView
from .processing import HEIF_AVAILABLE, Settings
from .exporting import safe_prefix
from .workers import Task
from .dropdata import drop_payload
from .diagnostics import log
from . import __version__

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def size_text(n):
    return f"{n / 1_000_000:.2f} MB" if n >= 1_000_000 else f"{n / 1000:.1f} KB"


def pixmap(im):
    return QPixmap.fromImage(ImageQt(im.convert("RGBA")))


class DropReceiver:
    """Recepción directa: evita que el modelo de la lista rechace archivos externos."""
    def dragEnterEvent(self, event):
        self.drop_owner.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.drop_owner.dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.drop_owner.dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_owner.dropEvent(event)


class DropZone(DropReceiver, QLabel):
    def __init__(self, owner, text):
        super().__init__(text)
        self.drop_owner = owner
        self.setAcceptDrops(True)


class ImageList(DropReceiver, QListWidget):
    def __init__(self, owner):
        super().__init__()
        self.drop_owner = owner
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#94a6b8"))
            painter.drawText(self.viewport().rect().adjusted(16, 16, -16, -16),
                             Qt.AlignCenter | Qt.TextWordWrap,
                             "Arrastra imágenes aquí\ndesde tu equipo o navegador")


class Comparison(QWidget):
    """Dos imágenes en el mismo rectángulo; el divisor revela la misma zona."""
    def __init__(self):
        super().__init__()
        self.before = self.after = None
        self.split = 50
        self.logo = QPixmap(str(ASSETS / "fotolista-logo.png"))
        self.setMinimumSize(360, 240)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101a24"))
        if self.before is None:
            side = min(144, self.height() // 2)
            logo_rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2 - 24, side, side)
            if not self.logo.isNull():
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawPixmap(logo_rect, self.logo, QRectF(self.logo.rect()))
            p.setPen(QColor("#94a6b8"))
            p.drawText(QRectF(0, logo_rect.bottom() + 14, self.width(), 40), Qt.AlignHCenter | Qt.AlignTop, "Selecciona una foto para compararla")
            return
        ratio = min(self.width() / self.before.width(), self.height() / self.before.height())
        w, h = self.before.width() * ratio, self.before.height() * ratio
        rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.drawPixmap(rect, self.before, QRectF(self.before.rect()))
        if self.after:
            boundary = rect.left() + w * self.split / 100
            p.save()
            p.setClipRect(QRectF(boundary, rect.top(), rect.right() - boundary, h))
            p.drawPixmap(rect, self.after, QRectF(self.after.rect()))
            p.restore()
            p.setPen(QColor("#63e2c3"))
            p.drawLine(int(boundary), int(rect.top()), int(boundary), int(rect.bottom()))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        if sys.platform == "win32" and not QFontDatabase.families():
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf"):
                QFontDatabase.addApplicationFont(str(fonts / name))
        self.setWindowTitle(f"FotoLista {__version__} · Prepara tus fotos")
        self.setWindowIcon(QIcon(str(ASSETS / "fotolista.ico")))
        self.resize(1220, 820)
        self.setMinimumSize(1000, 700)
        self.setAcceptDrops(True)
        self.task = None
        log.info("Ventana iniciada; revisión de arrastre 3")
        self.import_cache = TemporaryDirectory(prefix="fotolista-web-")
        self.records = {}
        self.destination = ""
        self.background = "#ffffff"
        self.errors = []
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "fotolista-logo.png")).scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(56, 56)
        header.addWidget(logo)
        brand = QLabel("FotoLista")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        privacy = QLabel("Local y sin cuentas")
        privacy.setObjectName("privacy")
        header.addWidget(privacy)
        layout.addLayout(header)
        self.drop = DropZone(self, "+  Arrastra imágenes desde tu equipo o navegador")
        self.drop.setObjectName("drop")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setMinimumHeight(65)
        layout.addWidget(self.drop)
        actions = QHBoxLayout()
        self.add = QPushButton("Añadir imágenes")
        self.remove = QPushButton("Quitar seleccionadas")
        self.add.clicked.connect(self.choose)
        self.remove.clicked.connect(self.remove_selected)
        actions.addWidget(self.add)
        actions.addWidget(self.remove)
        self.count = QLabel("0 fotografías")
        actions.addWidget(self.count)
        actions.addStretch()
        layout.addLayout(actions)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 12, 0)
        self.files = ImageList(self)
        self.files.setIconSize(QSize(82, 62))
        self.files.setSelectionMode(QListWidget.ExtendedSelection)
        self.files.currentItemChanged.connect(self.show_original)
        ll.addWidget(self.files)
        self.source_total = QLabel("Originales: 0 KB")
        ll.addWidget(self.source_total)
        splitter.addWidget(left)
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 12, 0)
        cl.addWidget(QLabel("VISTA PREVIA  ·  Original / Resultado"))
        self.comparison = Comparison()
        cl.addWidget(self.comparison, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self.move_split)
        cl.addWidget(self.slider)
        cl.addWidget(QLabel("Desliza para comparar la misma zona"))
        self.preview_info = QLabel("La vista previa usa los ajustes actuales.")
        self.preview_info.setWordWrap(True)
        cl.addWidget(self.preview_info)
        self.preview = QPushButton("Generar vista previa")
        self.preview.clicked.connect(self.make_preview)
        cl.addWidget(self.preview)
        splitter.addWidget(center)
        self.options = QFrame()
        self.options.setObjectName("options")
        form = QFormLayout(self.options)
        form.setSizeConstraint(QLayout.SetMinimumSize)
        form.setContentsMargins(16, 16, 16, 16)
        form.addRow(QLabel("PREPARAR FOTOGRAFÍAS"))
        self.fmt = QComboBox()
        self.fmt.addItems(["JPG", "PNG", "WebP"])
        form.addRow("Formato", self.fmt)
        self.limit = QComboBox()
        self.limit.addItems(["500 KB", "1 MB", "2 MB", "5 MB", "Personalizado", "Sin límite"])
        self.limit.setCurrentIndex(3)
        form.addRow("Máximo por foto", self.limit)
        self.custom = QSpinBox()
        self.custom.setRange(1, 1_000_000)
        self.custom.setValue(5000)
        self.custom.setSuffix(" KB")
        self.custom.setEnabled(False)
        form.addRow("Personalizado", self.custom)
        self.limit.currentIndexChanged.connect(lambda i: self.custom.setEnabled(i == 4))
        self.resize_check = QCheckBox("Redimensionar sin ampliar")
        form.addRow(self.resize_check)
        self.resize_mode = QComboBox()
        self.resize_mode.addItems(["Lado más largo", "Ancho"])
        form.addRow("Medida", self.resize_mode)
        self.pixels = QSpinBox()
        self.pixels.setRange(1, 50000)
        self.pixels.setValue(1920)
        self.pixels.setSuffix(" px")
        form.addRow("Tamaño máximo", self.pixels)
        self.color = QPushButton("Fondo JPG: blanco")
        self.color.clicked.connect(self.choose_color)
        form.addRow(self.color)
        self.metadata = QCheckBox("Eliminar metadatos personales")
        self.metadata.setChecked(True)
        form.addRow(self.metadata)
        self.rename = QCheckBox("Renombrar con numeración")
        form.addRow(self.rename)
        self.prefix = QLineEdit("Casa_Rialto")
        self.prefix.setMaxLength(120)
        form.addRow("Prefijo", self.prefix)
        note = QLabel("Cada foto cumple su propio límite.\nSi hace falta, se reduce la resolución.\nPNG usa compresión sin pérdida.\n1 MB = 1 000 000 bytes.")
        note.setWordWrap(True)
        form.addRow(note)
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setMinimumWidth(310)
        options_scroll.setWidget(self.options)
        splitter.addWidget(options_scroll)
        splitter.setSizes([280, 510, 320])
        folder = QHBoxLayout()
        self.folder_button = QPushButton("Elegir carpeta de destino")
        self.folder_button.clicked.connect(self.choose_folder)
        self.folder_label = QLabel("Selecciona dónde guardar las copias")
        self.folder_label.setWordWrap(True)
        folder.addWidget(self.folder_button)
        folder.addWidget(self.folder_label, 1)
        layout.addLayout(folder)
        self.results = QListWidget()
        self.results.setMaximumHeight(95)
        self.results.itemDoubleClicked.connect(self.open_result)
        layout.addWidget(self.results)
        self.status = QLabel("Tus originales siempre se conservan. Todo se procesa en tu equipo.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.export = QPushButton("Exportar fotografías  →")
        self.export.setObjectName("primary")
        self.export.clicked.connect(self.export_all)
        footer.addWidget(self.progress, 1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.export)
        layout.addLayout(footer)
        self.setStyleSheet(STYLE)
        # Los ajustes cambian el resultado: invalidar la comparación anterior.
        for widget in (self.fmt, self.limit, self.resize_mode):
            widget.currentIndexChanged.connect(self.invalidate)
        for widget in (self.custom, self.pixels):
            widget.valueChanged.connect(self.invalidate)
        for widget in (self.metadata, self.resize_check):
            widget.toggled.connect(self.invalidate)

    def invalidate(self, *_):
        self.comparison.after = None
        self.comparison.update()
        self.preview_info.setText("Genera la vista previa con los ajustes actuales.")

    def move_split(self, value):
        self.comparison.split = value
        self.comparison.update()

    def choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Añadir fotografías", "", "Imágenes (*.jpg *.jpeg *.png *.webp *.heic *.heif);;Todos los archivos (*)")
        self.load_paths(paths)

    def dragEnterEvent(self, event):
        log.info("Entrada de arrastre; ocupado=%s; formatos=%s", self.busy(), event.mimeData().formats())
        self.accept_drag(event)

    def accept_drag(self, event):
        # No leer imágenes ni descargarlas mientras se mueve el cursor.
        if not self.busy() and event.mimeData().formats():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self.drop.setProperty("dragActive", True)
            self.drop.style().unpolish(self.drop)
            self.drop.style().polish(self.drop)
            self.status.setText("Suelta la imagen para añadirla a FotoLista.")
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.accept_drag(event)

    def clear_drag_feedback(self):
        self.drop.setProperty("dragActive", False)
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def dragLeaveEvent(self, event):
        self.clear_drag_feedback()
        if not self.busy():
            self.status.setText("Arrastra una imagen a la franja superior o a la lista de fotos.")
        event.accept()

    def dropEvent(self, event):
        log.info("Archivo soltado; formatos=%s", event.mimeData().formats())
        self.clear_drag_feedback()
        if self.busy():
            event.ignore()
            return
        try:
            local, sources = drop_payload(event.mimeData())
            log.info("Datos recibidos; archivos=%d; imágenes web=%d", len(local), len(sources))
            # Capturar también fallos al normalizar rutas o iniciar el worker.
            if local:
                self.load_paths(local)
            elif sources:
                self.start(Task("import", sources, destination=self.import_cache.name), self.loaded)
            else:
                self.status.setText("No se recibió un archivo de imagen. Prueba con Añadir imágenes para seleccionarlo desde la carpeta.")
        except Exception as exc:
            log.exception("Fallo al recibir archivo soltado")
            self.status.setText(f"No se pudo recibir la imagen: {exc}")
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def busy(self):
        return self.task is not None

    def load_paths(self, paths):
        if self.busy():
            return
        paths = list(dict.fromkeys(str(Path(p).resolve()) for p in paths if p))
        paths = [p for p in paths if p not in self.records]
        if paths:
            self.start(Task("load", paths), self.loaded)
        else:
            self.status.setText("Esas imágenes ya están en la lista.")

    def loaded(self, record):
        path, fmt, dims, size, thumb = record
        self.records[path] = (fmt, dims, size, thumb)
        item = QListWidgetItem(QIcon(pixmap(thumb)), f"{Path(path).name}\n{fmt} · {dims[0]} × {dims[1]} · {size_text(size)}")
        item.setData(Qt.UserRole, path)
        self.files.addItem(item)
        if self.files.currentItem() is None:
            self.files.setCurrentItem(item)
        self.update_totals()
        log.info("Imagen añadida; total=%d", self.files.count())

    def update_totals(self):
        self.count.setText(f"{len(self.records)} fotografías")
        self.source_total.setText("Originales: " + size_text(sum(r[2] for r in self.records.values())))

    def remove_selected(self):
        if self.busy():
            return
        selected = self.files.selectedItems()
        if not selected:
            return
        # Actualizar la selección una sola vez, después de quitar todas las filas.
        self.files.blockSignals(True)
        try:
            for item in selected:
                self.records.pop(item.data(Qt.UserRole), None)
                self.files.takeItem(self.files.row(item))
        finally:
            self.files.blockSignals(False)
        self.update_totals()
        self.show_original(self.files.currentItem())
        self.slider.setValue(50)
        self.progress.setValue(0)
        remaining = len(self.records)
        self.status.setText(f"{remaining} fotografías en la lista." if remaining else "No hay fotografías en la lista. Añade o arrastra una imagen para comenzar.")

    def show_original(self, item, previous=None):
        self.invalidate()
        self.comparison.before = pixmap(self.records[item.data(Qt.UserRole)][3]) if item else None
        if item is None:
            self.preview_info.setText("Añade una fotografía para generar una vista previa.")
        self.comparison.update()

    def settings(self):
        limits = [500_000, 1_000_000, 2_000_000, 5_000_000, self.custom.value() * 1000, None]
        prefix = safe_prefix(self.prefix.text()) if self.rename.isChecked() else None
        return Settings(format=["JPEG", "PNG", "WEBP"][self.fmt.currentIndex()],
            limit=limits[self.limit.currentIndex()], pixels=self.pixels.value() if self.resize_check.isChecked() else None,
            resize_mode="width" if self.resize_mode.currentIndex() else "longest",
            strip_metadata=self.metadata.isChecked(), background=self.background, prefix=prefix)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.background), self, "Fondo para la transparencia en JPG")
        if color.isValid():
            self.background = color.name()
            self.color.setText("Fondo JPG: " + color.name())
            self.invalidate()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Guardar copias en…")
        if folder:
            self.destination = folder
            self.folder_label.setText(folder)

    def make_preview(self):
        item = self.files.currentItem()
        if not item or self.busy():
            return
        try:
            self.start(Task("preview", [item.data(Qt.UserRole)], self.settings()), self.preview_ready)
        except ValueError as exc:
            QMessageBox.warning(self, "Revisa los ajustes", str(exc))

    def preview_ready(self, payload):
        path, result = payload
        self.comparison.before = pixmap(result.preview_before)
        self.comparison.after = pixmap(result.preview_after)
        self.comparison.update()
        self.preview_info.setText(f"{size_text(self.records[path][2])} → {size_text(len(result.data))}\n{result.width} × {result.height} px · {result.format}")

    def export_all(self):
        if not self.records or self.busy():
            return
        if not self.destination:
            self.choose_folder()
        if not self.destination:
            return
        try:
            settings = self.settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Revisa los ajustes", str(exc))
            return
        self.results.clear()
        self.exported = self.input_bytes = self.output_bytes = 0
        paths = [self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())]
        self.start(Task("export", paths, settings, self.destination), self.export_ready)

    def export_ready(self, payload):
        source, target, result = payload
        self.exported += 1
        self.input_bytes += self.records[source][2]
        self.output_bytes += len(result.data)
        item = QListWidgetItem(f"✓ {target.name} · {size_text(len(result.data))} · {result.width} × {result.height} px")
        item.setData(Qt.UserRole, str(target))
        self.results.addItem(item)

    def open_result(self, item):
        path = item.data(Qt.UserRole)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def start(self, task, receiver):
        log.info("Tarea iniciada; modo=%s; cantidad=%d", task.mode, len(task.paths))
        self.errors = []
        self.task = task
        self.stopped = False
        task.item.connect(receiver)
        task.failed.connect(self.task_error)
        task.progress.connect(lambda n, total: self.progress.setValue(round(n * 100 / total)))
        task.outcome.connect(self.set_outcome)
        task.finished.connect(self.finished)
        self.progress.setValue(0)
        self.status.setText({"load": "Leyendo fotografías…", "import": "Importando imagen del navegador…", "preview": "Preparando comparación…", "export": "Exportando copias…"}[task.mode])
        for widget in (self.options, self.add, self.remove, self.preview, self.export, self.folder_button, self.files):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        task.start()

    def task_error(self, message):
        log.warning("Fallo durante tarea %s", self.task.mode if self.task else "sin tarea")
        self.errors.append(message)
        self.results.addItem("⚠ " + message)
        self.status.setText(message)

    def set_outcome(self, stopped):
        self.stopped = stopped

    def finished(self):
        mode = self.task.mode
        log.info("Tarea finalizada; modo=%s; errores=%d; fotos=%d", mode, len(self.errors), len(self.records))
        self.task.deleteLater()
        self.task = None
        for widget in (self.options, self.add, self.remove, self.preview, self.export, self.folder_button, self.files):
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        prefix = "Cancelado" if self.stopped else ("Finalizado con errores" if self.errors else "Finalizado")
        if mode == "export":
            saving = self.input_bytes - self.output_bytes
            change = f"Ahorro: {size_text(saving)}" if saving >= 0 else f"Incremento por conversión: {size_text(-saving)}"
            self.status.setText(f"{prefix} · {self.exported} copias guardadas · {size_text(self.input_bytes)} → {size_text(self.output_bytes)} · {change} · {len(self.errors)} errores. Doble clic en un resultado para abrirlo.")
        else:
            if self.errors:
                self.status.setText(f"{prefix}: {self.errors[-1]}")
            elif mode in ("load", "import"):
                self.status.setText(f"{prefix} · {len(self.records)} fotografías en la lista.")
            else:
                self.status.setText(prefix)

    def cancel_task(self):
        if self.task:
            self.task.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelando… Esperando a que termine la operación de imagen actual.")

    def closeEvent(self, event):
        if self.busy():
            self.cancel_task()
            self.status.setText("Cancelando… Cierra la ventana cuando termine la tarea.")
            event.ignore()
        else:
            self.import_cache.cleanup()
            event.accept()


STYLE = """
QWidget { background: #111c27; color: #dce7f1; font: 10pt 'Segoe UI'; }
QLabel, QCheckBox { background: transparent; }
QScrollArea { border: 0; }
QLabel#brand { font: 26pt 'Segoe UI'; font-weight: 700; }
QLabel#privacy { font: 13pt 'Segoe UI'; font-weight: 700; }
QLabel#drop { border: 2px dashed #3a756e; border-radius: 12px; background: #162d34; color: #9de9d5; }
QLabel#drop[dragActive="true"] { border: 2px solid #65dfbf; background: #254e50; }
QFrame#options { background: #1a2937; border-radius: 12px; }
QPushButton { background: #253a4b; border: 1px solid #375268; padding: 9px 13px; border-radius: 7px; }
QPushButton:hover { background: #34566a; }
QPushButton:disabled { color: #71808e; background: #1c2b38; }
QPushButton#primary { background: #65dfbf; color: #092f29; font-weight: 700; padding: 12px 22px; }
QListWidget, QLineEdit, QSpinBox, QComboBox { background: #162532; border: 1px solid #344a5e; border-radius: 6px; padding: 6px; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #283a49; }
QListWidget::item:selected { background: #2c5559; }
QProgressBar { border: 0; background: #253a4b; border-radius: 6px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #318e7c; border-radius: 6px; }
QCheckBox { padding: 4px 0; }
QSlider::groove:horizontal { height: 5px; background: #365469; }
QSlider::handle:horizontal { background: #65dfbf; width: 16px; margin: -6px 0; border-radius: 8px; }
"""

STYLE += """
QScrollBar:vertical { background: #203342; width: 18px; margin: 20px 0; border-radius: 7px; }
QScrollBar:horizontal { background: #203342; height: 18px; margin: 0 20px; border-radius: 7px; }
QScrollBar::handle:vertical { background: #61979e; min-height: 36px; border: 3px solid #203342; border-radius: 7px; }
QScrollBar::handle:horizontal { background: #61979e; min-width: 36px; border: 3px solid #203342; border-radius: 7px; }
QScrollBar::handle:hover, QScrollBar::handle:pressed { background: #80efd0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar::add-line:vertical { subcontrol-origin: margin; subcontrol-position: bottom; height: 20px; background: #314e62; border-radius: 4px; }
QScrollBar::sub-line:vertical { subcontrol-origin: margin; subcontrol-position: top; height: 20px; background: #314e62; border-radius: 4px; }
QScrollBar::add-line:horizontal { subcontrol-origin: margin; subcontrol-position: right; width: 20px; background: #314e62; border-radius: 4px; }
QScrollBar::sub-line:horizontal { subcontrol-origin: margin; subcontrol-position: left; width: 20px; background: #314e62; border-radius: 4px; }
QScrollBar::add-line:hover, QScrollBar::sub-line:hover { background: #467386; }
QSpinBox { padding-right: 32px; min-height: 26px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; background: #314e62; border-left: 1px solid #577c90; border-top-right-radius: 5px; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; background: #314e62; border-left: 1px solid #577c90; border-top: 1px solid #577c90; border-bottom-right-radius: 5px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #467386; }
QSpinBox:disabled { color: #8294a3; }
QComboBox { padding-right: 32px; min-height: 26px; }
QComboBox::drop-down { width: 28px; border-left: 1px solid #577c90; background: #314e62; border-top-right-radius: 5px; border-bottom-right-radius: 5px; }
QComboBox::drop-down:hover { background: #467386; }
QAbstractScrollArea::corner { background: #203342; }
QSlider::groove:horizontal { height: 6px; background: #527386; border-radius: 3px; }
QSlider::handle:horizontal { background: #80efd0; width: 20px; margin: -7px 0; border: 1px solid #a8f5df; border-radius: 10px; }
"""
STYLE += f"""
QScrollBar::up-arrow, QSpinBox::up-arrow {{ image: url("{ASSETS.as_posix()}/arrow-up.svg"); width: 12px; height: 8px; }}
QScrollBar::down-arrow, QSpinBox::down-arrow, QComboBox::down-arrow {{ image: url("{ASSETS.as_posix()}/arrow-down.svg"); width: 12px; height: 8px; }}
QScrollBar::left-arrow {{ image: url("{ASSETS.as_posix()}/arrow-left.svg"); width: 8px; height: 12px; }}
QScrollBar::right-arrow {{ image: url("{ASSETS.as_posix()}/arrow-right.svg"); width: 8px; height: 12px; }}
"""


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("FotoLista")
    window = Window()
    if sys.platform == "win32":
        try:
            import ctypes
            elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
            log.info("Permisos elevados=%s", elevated)
            if elevated:
                window.status.setText("Para arrastrar fotos desde una carpeta, cierra FotoLista y ábrela desde Inicio o el Explorador, sin usar Ejecutar como administrador.")
        except (AttributeError, OSError):
            log.exception("No se pudo comprobar el nivel de permisos")
    def report_exception(kind, value, traceback):
        log.error("Excepción de interfaz", exc_info=(kind, value, traceback))
        window.status.setText(f"No se pudo completar la acción: {value}. Se guardó el detalle en registro-fotolista.log.")
    sys.excepthook = report_exception
    window.show()
    sys.exit(app.exec())
