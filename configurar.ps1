param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& $Python -c "import sys,struct; assert (3,10) <= sys.version_info[:2] <= (3,14) and struct.calcsize('P')==8, 'Usa Python de 64 bits entre 3.10 y 3.14'; print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw 'Python no compatible o no disponible.' }
if (!(Test-Path '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
}
& '.\.venv\Scripts\python.exe' -m pip install --dry-run --only-binary=:all: -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No hay dependencias binarias compatibles. Prueba Python 3.12 de 64 bits.' }
& '.\.venv\Scripts\python.exe' -m pip install --only-binary=:all: -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
Write-Host 'Listo. Abre Iniciar.cmd para ejecutar FotoLista.'
