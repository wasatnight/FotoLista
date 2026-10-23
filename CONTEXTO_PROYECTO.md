# Contexto de FotoLista

Versión: 1.0.2. Autor del proyecto: Ivan Solano.

## Objetivo y alcance

Preparar fotografías localmente en Windows para páginas web o compartirlas. Reducir cada archivo a un máximo configurable, redimensionar y convertir formatos por lotes conservando los originales. Aplicación gratuita, sin cuentas ni funciones bloqueadas.

## Decisiones técnicas

Python 3.12 x64, PySide6, Pillow y pillow-heif; versiones exactas en requirements-validated.txt. Interfaz, motor, importación y exportación separados. QThread procesa un archivo a resolución completa por vez. JPG/WebP buscan calidad entre 45 y 95 y reducen dimensiones si hace falta; PNG mantiene compresión sin pérdida. KB/MB decimales. La exportación usa temporales completos y publicación exclusiva sin sobrescribir.

## Funciones implementadas

Carga por arrastre y selector, miniaturas, límites por archivo, redimensionado proporcional sin ampliación, JPG/PNG/WebP, lectura HEIC, fondo JPG, eliminación de metadatos, prefijo con numeración, comparación, exportación segura, cancelación y resumen. Al quitar la última foto se limpia el estado. Flechas y barras con mayor contraste.

## Distribución y validación

PyInstaller usa FotoLista.spec. Se excluye una copia de icuuc.dll ajena que podía recogerse desde PATH e impedía cargar Qt. Se usa el ICU de Windows. Inno Setup crea el instalador por usuario. La app debe ejecutarse sin administrador para recibir el arrastre del Explorador normal.

23 pruebas aprobadas; diagnóstico del EXE con PATH sin Python correcto; instalación, arranque instalado y desinstalación aisladas correctos. Una imagen sintética de 32.9 MB quedó en 4.95 MB al elegir máximo 5 MB, con hash original intacto. Falta validar accesos de Inicio/escritorio y registro de desinstalación en un equipo Windows limpio, y probar más HEIC/HDR reales.

## Comandos

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\empaquetar.ps1
.\crear-instalador.ps1
```

## Pendientes

Firma de editor y distribución certificada: no se garantiza evitar avisos de Windows; Microsoft Store requiere cuenta del propietario y certificación. Pendiente definir la licencia del código propio. No hay zoom 1:1 ni soporte de animaciones/multipágina; gestión de HDR/CMYK necesita pruebas. Marcas de agua, recortes sociales, presets avanzados, donaciones y actualizaciones automáticas siguen fuera de esta versión.

## Estado para retomar

Este repositorio contiene fuentes y recursos, sin entornos virtuales, registros locales ni ejecutables. Tras modificar producción, ejecutar las pruebas y reconstruir el paquete. Mantener los instaladores y portables en Releases. No incorporar archivos personales ni certificados al repositorio.
