@echo off
chcp 65001 >nul 2>&1
title Chopo Merida - Actualizar y Publicar en la Nube

cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"

echo ===================================================================
echo   SINCRONIZADOR AUTOMATICO DE PRECIOS - CHOPO MERIDA
echo ===================================================================
echo   Este proceso hara todo de forma automatica en 3 pasos:
echo.
echo     [1/3] Descarga precios frescos de Chopo Merida Altabrisa
echo     [2/3] Verifica y actualiza detalles de los 152 paquetes
echo     [3/3] Sube los datos a GitHub y actualiza Streamlit Cloud
echo.
echo   La nube (https://chopo-merida-precios.streamlit.app/)
echo   se actualizara sola sin que tengas que hacer nada mas.
echo ===================================================================
echo.
echo Presiona cualquier tecla para comenzar o cierra esta ventana...
pause >nul

echo.
echo ===================================================================
echo   PASO 1/3: Extrayendo catalogo completo de Chopo Merida...
echo   (El navegador automatizado puede tomar entre 10 y 15 minutos)
echo ===================================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en venv\Scripts\python.exe
    pause
    exit /b 1
)

call venv\Scripts\python.exe main.py scrape
if %errorlevel% neq 0 (
    echo.
    echo [ADVERTENCIA] El scraper finalizo con advertencias o error.
    echo Intentando continuar con la sincronizacion...
)

echo.
echo ===================================================================
echo   PASO 2/3: Verificando nuevos paquetes y actualizando detalles...
echo ===================================================================
echo.

call venv\Scripts\python.exe -c "from scraper.scrape_bundle_details import run_bundle_scraper; tot, done = run_bundle_scraper(force=False); print(f'[OK] Paquetes verificados: {tot} (Nuevos procesados: {done})')"

echo.
echo ===================================================================
echo   PASO 3/3: Publicando cambios en GitHub y Streamlit Cloud...
echo ===================================================================
echo.

git add db/chopo_prices.db exports/
git commit -m "Auto-update precios Chopo Merida: %date% %time%" >nul 2>&1

echo Subiendo datos a GitHub...
git push origin main

if %errorlevel% equ 0 (
    echo.
    echo ===================================================================
    echo   EXITO TOTAL: BASE DE DATOS ACTUALIZADA Y PUBLICADA
    echo ===================================================================
    echo   1. Los precios locales han sido guardados.
    echo   2. El repositorio en GitHub fue actualizado.
    echo   3. En aproximadamente 30 segundos, tu dashboard publico en la nube reflejara
    echo      los nuevos precios para todos tus usuarios y colegas:
    echo.
    echo      https://chopo-merida-precios.streamlit.app/
    echo ===================================================================
) else (
    echo.
    echo ===================================================================
    echo   [!] Hubo un problema al subir a GitHub.
    echo   Verifica tu conexion a internet o tus credenciales de Git.
    echo   Tus datos locales SI fueron guardados correctamente en:
    echo   db/chopo_prices.db
    echo ===================================================================
)

echo.
echo Presiona cualquier tecla para salir...
pause >nul