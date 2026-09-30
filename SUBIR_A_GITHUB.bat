@echo off
chcp 65001 >nul 2>&1
title Subir Cambios a GitHub - Chopo Precios

cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%LOCALAPPDATA%\Programs\Git\mingw64\bin;%PATH%"

echo ============================================================
echo   SUBIENDO PROYECTO A GITHUB (robercrz/chopo-precios)
echo ============================================================
echo.

git add dashboard/ scraper/ config/ db/*.py requirements.txt requirements-scraper.txt *.bat README.md
git commit -m "Actualizacion de codigo y mejoras" >nul 2>&1
echo Enviando cambios a GitHub...
git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ============================================================
    echo   [OK] Proyecto subido exitosamente a GitHub!
    echo   Streamlit Cloud se actualizara en breve automaticamente.
    echo ============================================================
) else (
    echo ============================================================
    echo   [!] Hubo un detalle al subir los cambios.
    echo   Si te abrio una ventana de navegador para autorizar
    echo   GitHub, dale clic en autorizar y vuelve a ejecutarlo.
    echo ============================================================
)

echo.
pause
