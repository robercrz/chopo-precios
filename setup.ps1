#!/usr/bin/env pwsh
# ============================================================
# setup.ps1 - Script de instalación completo (Windows PowerShell)
# ============================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       Chopo Price Intelligence - Instalación          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ── 1. Verificar Python ────────────────────────────────────────────────────────
Write-Host "📦 Verificando Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "   ✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Python no encontrado. Instala Python 3.9+ desde python.org" -ForegroundColor Red
    exit 1
}

# ── 2. Crear entorno virtual ───────────────────────────────────────────────────
Write-Host ""
Write-Host "🔧 Creando entorno virtual..." -ForegroundColor Yellow
$venvPath = Join-Path $ScriptDir "venv"
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
    Write-Host "   ✅ Entorno virtual creado en: $venvPath" -ForegroundColor Green
} else {
    Write-Host "   ℹ️  Entorno virtual ya existe" -ForegroundColor Cyan
}

# ── 3. Activar entorno virtual ─────────────────────────────────────────────────
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
& $activateScript

# ── 4. Actualizar pip ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "📦 Actualizando pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
Write-Host "   ✅ pip actualizado" -ForegroundColor Green

# ── 5. Instalar dependencias ───────────────────────────────────────────────────
Write-Host ""
Write-Host "📥 Instalando dependencias..." -ForegroundColor Yellow
$reqPath = Join-Path $ScriptDir "requirements.txt"
pip install -r $reqPath
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Dependencias instaladas" -ForegroundColor Green
} else {
    Write-Host "   ❌ Error instalando dependencias" -ForegroundColor Red
    exit 1
}

# ── 6. Instalar Playwright browsers ───────────────────────────────────────────
Write-Host ""
Write-Host "🌐 Instalando navegador Chromium para Playwright..." -ForegroundColor Yellow
python -m playwright install chromium
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ Chromium instalado" -ForegroundColor Green
} else {
    Write-Host "   ❌ Error instalando Playwright" -ForegroundColor Red
    exit 1
}

# ── 7. Inicializar base de datos ───────────────────────────────────────────────
Write-Host ""
Write-Host "🗄️  Inicializando base de datos..." -ForegroundColor Yellow
python (Join-Path $ScriptDir "main.py") init
Write-Host "   ✅ Base de datos lista" -ForegroundColor Green

# ── 8. Crear archivos __init__.py ──────────────────────────────────────────────
"" | Out-File (Join-Path $ScriptDir "scraper\__init__.py") -Encoding UTF8
"" | Out-File (Join-Path $ScriptDir "db\__init__.py") -Encoding UTF8
"" | Out-File (Join-Path $ScriptDir "dashboard\__init__.py") -Encoding UTF8

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              ✅ Instalación completada!               ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Próximos pasos:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Ejecutar scrape inicial:" -ForegroundColor Yellow
Write-Host "     python main.py scrape" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Lanzar el dashboard:" -ForegroundColor Yellow
Write-Host "     python main.py dashboard" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Iniciar actualizaciones automáticas diarias:" -ForegroundColor Yellow
Write-Host "     python main.py scheduler" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Exportar a Excel:" -ForegroundColor Yellow
Write-Host "     python main.py export" -ForegroundColor Cyan
Write-Host ""
