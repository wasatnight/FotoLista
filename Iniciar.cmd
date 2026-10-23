@echo off
cd /d "%~dp0"
if exist "dist\FotoLista\FotoLista.exe" (
    start "" "dist\FotoLista\FotoLista.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b
)
echo Ejecuta primero configurar.ps1, o utiliza la distribucion compilada.
pause
