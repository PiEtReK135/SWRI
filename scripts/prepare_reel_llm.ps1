param([string]$Data = $(if ($env:IW_DATA) { $env:IW_DATA } else { "data" }))

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Get-VerifiedFile([string]$Url, [string]$Destination, [string]$Sha256) {
    if ((Test-Path -LiteralPath $Destination) -and (Get-FileHash -LiteralPath $Destination).Hash -eq $Sha256) {
        return
    }
    $Partial = "$Destination.part"
    & curl.exe --fail --location --silent --show-error --retry 2 $Url --output $Partial
    if ($LASTEXITCODE -ne 0) { throw "Pobieranie nie powiodlo sie: $Url" }
    if ((Get-FileHash -LiteralPath $Partial).Hash -ne $Sha256) { throw "Niepoprawna suma SHA256: $Partial" }
    Move-Item -LiteralPath $Partial -Destination $Destination -Force
}

$Models = Join-Path $Data "models"
$Tools = Join-Path $Data "tools"
New-Item -ItemType Directory -Force -Path $Models, $Tools | Out-Null
$Runtime = Join-Path $Tools "llama-b12602"
if (-not (Test-Path (Join-Path $Runtime "llama-server.exe"))) {
    $Zip = Join-Path $Tools "llama-b12602-cpu.zip"
    $Url = "https://github.com/ggml-org/llama.cpp/releases/download/b12602/llama-b12602-bin-win-cpu-x64.zip"
    Get-VerifiedFile $Url $Zip "9957dab2f52e2599b85921ef3e2661287c1f3ad302bc0be07992e915cc6f7392"
    Expand-Archive -LiteralPath $Zip -DestinationPath $Runtime -Force
}
$Url = "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae/Qwen3.5-2B-Q4_K_M.gguf?download=true"
Get-VerifiedFile $Url (Join-Path $Models "qwen3.5-2b-q4_k_m.gguf") "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"
