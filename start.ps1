param([switch]$WithASR, [switch]$Install, [string]$SiteDir, [switch]$WithOllama)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:Path = @($env:Path, [Environment]::GetEnvironmentVariable("Path", "Machine"),
              [Environment]::GetEnvironmentVariable("Path", "User")) -join ";"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $Install = $true
}
$Python = ".\.venv\Scripts\python.exe"
if ($Install -or $WithASR) {
    & $Python -m pip install pip==26.2.2
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $Requirements = @("-r", "requirements.txt")
    if ($WithASR) { $Requirements += @("-r", "requirements-ai.txt") }
    & $Python -m pip install @Requirements
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$Tesseract = Join-Path $env:ProgramFiles "Tesseract-OCR"
if (Test-Path $Tesseract) { $env:Path = "$Tesseract;$env:Path" }
$Data = if ($env:IW_DATA) { $env:IW_DATA } else { "data" }
$LocalTessdata = Join-Path $Data "tessdata"
if (Test-Path (Join-Path $LocalTessdata "pol.traineddata")) {
    $env:TESSDATA_PREFIX = (Resolve-Path $LocalTessdata).Path
}
$LocalModel = Join-Path $Data "models/whisper-base"
if (-not $env:IW_WHISPER_MODEL -and (Test-Path (Join-Path $LocalModel "model.bin"))) {
    $env:IW_WHISPER_MODEL = (Resolve-Path $LocalModel).Path
}
if ($SiteDir) { $env:IW_SITE_DIR = (Resolve-Path $SiteDir).Path }
if ($WithOllama) { $env:IW_OLLAMA_MODEL = "qwen3:1.7b" }
& $Python -m uvicorn investwatch.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
exit $LASTEXITCODE
