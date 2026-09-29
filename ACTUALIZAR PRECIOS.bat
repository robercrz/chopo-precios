@echo off
chcp 65001 >nul 2>&1
title Chopo - Actualizar Precios

cd /d "%~dp0"

echo ============================================================
echo   Actualizando precios de Chopo Merida Altabrisa...
echo   (Este proceso tarda aproximadamente 15 minutos)
echo ============================================================
echo.

call venv\Scripts\python main.py scrape

echo.
echo ============================================================
echo   Actualizacion terminada. Puedes cerrar esta ventana.
echo ============================================================
echo.
pause
