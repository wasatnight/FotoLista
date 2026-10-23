$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& '.\.venv\Scripts\python.exe' -m pip install --only-binary=:all: -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Error al instalar dependencias de empaquetado.' }
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Las pruebas fallaron.' }
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --clean FotoLista.spec
if ($LASTEXITCODE -ne 0) { throw 'Error al empaquetar.' }
Write-Host 'Distribuye TODA la carpeta dist\FotoLista, incluido _internal.'
