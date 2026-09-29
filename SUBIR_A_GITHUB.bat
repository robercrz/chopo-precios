@echo off
chcp 65001 >nul 2>&1
title Subir Cambios a GitHub - Chopo Precios

cd /d "C:\Users\rober\Documents\proyeto test 1\chopo_scraper"

echo ============================================================
echo   SUBIENDO PROYECTO A GITHUB (robercrz/chopo-precios)
echo ============================================================
echo.

git add .
git commit -m "Actualizacion de base de datos y mejoras" >nul 2>&1
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
