@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Chopo Price Intelligence — Instalador

echo.
echo ============================================================
echo   CHOPO PRICE INTELLIGENCE
echo   Instalador automatico para Windows
echo ============================================================
echo.

REM ── 1. Verificar Python ──────────────────────────────────────
echo [1/6] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Python no esta instalado en esta computadora.
    echo.
    echo  Por favor instala Python 3.9 o superior desde:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: Marca la casilla "Add Python to PATH"
    echo  durante la instalacion.
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo    OK - Python %PYVER% encontrado

REM ── 2. Crear entorno virtual ─────────────────────────────────
echo.
echo [2/6] Creando entorno virtual...
if exist "venv\" (
    echo    OK - Entorno virtual ya existe, omitiendo...
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo    ERROR al crear entorno virtual
        pause
        exit /b 1
    )
    echo    OK - Entorno virtual creado
)

REM ── 3. Instalar dependencias ─────────────────────────────────
echo.
echo [3/6] Instalando dependencias (puede tardar 2-5 minutos)...
call venv\Scripts\pip install --quiet --upgrade pip
call venv\Scripts\pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo    ERROR al instalar dependencias
    pause
    exit /b 1
)
echo    OK - Dependencias instaladas

REM ── 4. Instalar navegador Playwright ─────────────────────────
echo.
echo [4/6] Descargando navegador para scraping (Chromium ~180MB)...
echo    Esto solo se hace una vez...
call venv\Scripts\playwright install chromium
if %errorlevel% neq 0 (
    echo    ERROR al instalar Playwright
    pause
    exit /b 1
)
echo    OK - Navegador instalado

REM ── 5. Inicializar base de datos ─────────────────────────────
echo.
echo [5/6] Inicializando base de datos...
call venv\Scripts\python main.py init >nul 2>&1
echo    OK - Base de datos lista

REM ── 6. Crear acceso directo en el Escritorio ─────────────────
echo.
echo [6/6] Creando accesos directos en el Escritorio...

set SCRIPT_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

REM Acceso directo para el Dashboard
(
echo @echo off
echo chcp 65001 ^>nul 2^>^&1
echo title Chopo Price Intelligence
echo cd /d "%SCRIPT_DIR%"
echo echo Iniciando dashboard...
echo start "" "http://localhost:8501"
echo timeout /t 3 /nobreak ^>nul
echo call venv\Scripts\python main.py dashboard
) > "%DESKTOP%\Chopo Dashboard.bat"

REM Acceso directo para Actualizar Precios
(
echo @echo off
echo chcp 65001 ^>nul 2^>^&1
echo title Chopo - Actualizar Precios
echo cd /d "%SCRIPT_DIR%"
echo echo Actualizando precios de Chopo Merida Altabrisa...
echo call venv\Scripts\python main.py scrape
echo echo.
echo echo Listo. Puedes cerrar esta ventana.
echo pause
) > "%DESKTOP%\Actualizar Precios Chopo.bat"

echo    OK - Accesos directos creados en el Escritorio

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo   Se crearon 2 iconos en tu Escritorio:
echo.
echo   [Chopo Dashboard]          - Abre el panel de precios
echo   [Actualizar Precios Chopo] - Descarga precios actuales
echo.
echo   PRIMER USO:
echo   1. Haz doble clic en "Actualizar Precios Chopo"
echo      (tarda ~15 min la primera vez)
echo   2. Luego abre "Chopo Dashboard"
echo.
echo ============================================================
echo.
set /p OPEN="¿Abrir el Dashboard ahora? (s/n): "
if /i "%OPEN%"=="s" (
    start "" "http://localhost:8501"
    start "" cmd /c "cd /d "%SCRIPT_DIR%" && call venv\Scripts\python main.py dashboard"
)

endlocal
