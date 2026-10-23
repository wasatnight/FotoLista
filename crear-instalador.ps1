param([string]$ISCC = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path 'dist\FotoLista\FotoLista.exe')) { throw 'Ejecuta empaquetar.ps1 primero.' }
if (!$ISCC) {
    $taskCompiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($taskCompiler) { $ISCC = $taskCompiler.Source }
}
if (!$ISCC) {
    foreach ($taskCandidate in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 7\ISCC.exe")) {
        if (Test-Path -LiteralPath $taskCandidate) { $ISCC = (Resolve-Path -LiteralPath $taskCandidate).Path; break }
    }
}
if (!$ISCC) { throw 'Instala Inno Setup desde jrsoftware.org o indica la ruta con -ISCC.' }
& $ISCC 'installer\FotoLista.iss'
if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el instalador.' }
