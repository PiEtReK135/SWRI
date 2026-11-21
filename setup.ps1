param([switch]$SkipModels, [switch]$WithOllama)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Checked($Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Polecenie $Command zakończyło się kodem $LASTEXITCODE." }
}

function Refresh-Path {
    $Machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $User = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$Machine;$User;$env:Path"
    $Tesseract = Join-Path $env:ProgramFiles "Tesseract-OCR"
    if (Test-Path $Tesseract) { $env:Path = "$Tesseract;$env:Path" }
}

function Install-Package($Id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Brak winget. Zainstaluj Instalator aplikacji z Microsoft Store."
    }
    Invoke-Checked winget @("install", "--id", $Id, "--exact", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity")
    Refresh-Path
}

function Test-Python312 {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { return $false }
    $ErrorActionPreference = "Continue"
    & py -3.12 -c "import sys; print(sys.version)" 2>$null | Out-Host
    return $LASTEXITCODE -eq 0
}

Refresh-Path
if (-not (Test-Python312)) { Install-Package "Python.Python.3.12" }
if (-not ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and
          (Get-Command ffprobe -ErrorAction SilentlyContinue))) { Install-Package "Gyan.FFmpeg" }
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) { Install-Package "UB-Mannheim.TesseractOCR" }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Checked py @("-3.12", "-m", "venv", ".venv")
}
$Python = ".\.venv\Scripts\python.exe"
Invoke-Checked $Python @("-m", "pip", "install", "pip==26.2.2")
Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-ai.txt")
Invoke-Checked $Python @("scripts/prepare_assets.py")

if (-not $SkipModels) {
    try { Invoke-Checked $Python @("scripts/prepare_assets.py", "--models") }
    catch { Write-Warning "Model Whisper nie został przygotowany. Aplikacja może analizować napisy i OCR. $($_.Exception.Message)" }
}

if ($WithOllama) {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Install-Package "Ollama.Ollama" }
    Invoke-Checked ollama @("pull", "qwen3:1.7b")
}
Write-Output "Uruchom .\start.ps1"
