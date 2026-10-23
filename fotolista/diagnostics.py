"""Registro local de fallos; no guarda imágenes, enlaces ni rutas de fotos."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import sys


def create_logger():
    logger = logging.getLogger("fotolista")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    folder = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FotoLista"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "registro-fotolista.log", maxBytes=250_000, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


log = create_logger()
