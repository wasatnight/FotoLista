# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

project = Path(SPECPATH).resolve()
datas, binaries, hiddenimports = collect_all("pillow_heif")
datas += [(str(project / "assets"), "assets")]
for package in ("PySide6_Essentials", "shiboken6", "Pillow", "pillow-heif"):
    datas += copy_metadata(package)
datas += [(str(project / "TERCEROS.md"), ".")]

a = Analysis([str(project / "main.py")], pathex=[str(project)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
# Qt enlaza el ICU de Windows (símbolos sin sufijo). El ICU de Poppler en PATH
# exporta símbolos con sufijo y no puede sustituir al de Windows en el paquete.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in {"icuuc.dll", "icudt78.dll"}]
a.datas += [("licenses/" + file.name, str(file), "DATA")
            for file in (project / "licenses").iterdir() if file.is_file()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FotoLista",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon=str(project / "assets" / "fotolista.ico"),
          version=str(project / "installer" / "version-info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FotoLista")
