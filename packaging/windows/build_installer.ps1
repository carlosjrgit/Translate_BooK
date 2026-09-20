<#
.SYNOPSIS
    Script de build para empacotamento Windows e geração do instalador do Translate_BooK.

.DESCRIPTION
    1. Limpa diretórios temporários de build (dist, build).
    2. Executa PyInstaller com packaging/windows/translate_book.spec.
    3. Verifica que nenhum arquivo de modelo de IA foi embutido na pasta dist.
    4. Compila o instalador via Inno Setup (ISCC.exe) se estiver disponível no PATH ou em locais padrão.

.NOTES
    Não exige privilégios administrativos.
#>

param (
    [switch]$SkipInstaller = $false
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Translate_BooK - Pipeline de Empacotamento Windows       " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$WorkspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $WorkspaceRoot

$DistDir = Join-Path $WorkspaceRoot "dist\Translate_BooK"
$InstallerOutDir = Join-Path $WorkspaceRoot "dist_installer"
$SpecFile = Join-Path $PSScriptRoot "translate_book.spec"
$IssFile = Join-Path $PSScriptRoot "installer.iss"

# 1. Limpeza de artefatos anteriores
Write-Host "`n[1/4] Limpando builds anteriores..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (-not (Test-Path $InstallerOutDir)) { New-Item -ItemType Directory -Path $InstallerOutDir | Out-Null }

# 2. Execução do PyInstaller
Write-Host "`n[2/4] Executando PyInstaller com $SpecFile..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm "$SpecFile"

if (-not (Test-Path "$DistDir\Translate_BooK.exe")) {
    Write-Error "Falha ao gerar o executável Translate_BooK.exe!"
    exit 1
}
Write-Host "  -> Binário standalone gerado com sucesso em: $DistDir" -ForegroundColor Green

# 3. Auditoria de Segurança: Certificar que NENHUM peso de IA foi embutido
Write-Host "`n[3/4] Auditando integridade do pacote (zero pesos neurais)..." -ForegroundColor Yellow
$IllegalWeights = Get-ChildItem -Path $DistDir -Recurse -Include *.bin, *.safetensors, *.gguf, *.onnx, *.pt, *.pth
if ($IllegalWeights.Count -gt 0) {
    Write-Error "ERRO CRÍTICO: Pesos neurais detectados no diretório dist:`n$($IllegalWeights.FullName -join "`n")"
    exit 1
}
Write-Host "  -> Auditoria aprovada: Nenhum peso de IA embutido." -ForegroundColor Green

# 4. Compilação do Instalador via Inno Setup
if ($SkipInstaller) {
    Write-Host "`n[4/4] Geração de instalador ignorada (-SkipInstaller)." -ForegroundColor Gray
    exit 0
}

Write-Host "`n[4/4] Compilando instalador Inno Setup..." -ForegroundColor Yellow

$ISCC_Candidates = @(
    "iscc.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
)

$ISCC_Path = $null
foreach ($cand in $ISCC_Candidates) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        $ISCC_Path = $cand
        break
    } elseif (Test-Path $cand) {
        $ISCC_Path = $cand
        break
    }
}

if ($ISCC_Path) {
    Write-Host "  -> Usando Inno Setup Compiler em: $ISCC_Path" -ForegroundColor Green
    & $ISCC_Path "$IssFile"
    Write-Host "`nInstalador compilado com sucesso em: $InstallerOutDir" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup (ISCC.exe) não foi encontrado no sistema."
    Write-Warning "Para gerar o arquivo de setup .exe, instale o Inno Setup 6 e execute:"
    Write-Warning "  iscc.exe '$IssFile'"
    Write-Host "O pacote portátil em 'dist\Translate_BooK' está pronto para uso e testes." -ForegroundColor Cyan
}

Write-Host "`nProcesso concluído!" -ForegroundColor Cyan
