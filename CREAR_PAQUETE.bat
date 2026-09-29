@echo off
chcp 65001 >nul 2>&1
title Crear paquete de distribucion

cd /d "%~dp0"

echo Creando ZIP de distribucion...

REM Crear directorio temporal
set DIST_DIR=%TEMP%\chopo_dist
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%\chopo_scraper"

REM Copiar archivos (excluir venv, __pycache__, BD, logs de imagen)
xcopy /E /I /Y /EXCLUDE:build_exclude.txt . "%DIST_DIR%\chopo_scraper" >nul

REM Crear el ZIP en el Escritorio
set ZIP_NAME=%USERPROFILE%\Desktop\Chopo_Price_Intelligence.zip
if exist "%ZIP_NAME%" del "%ZIP_NAME%"

powershell -command "Compress-Archive -Path '%DIST_DIR%\chopo_scraper' -DestinationPath '%ZIP_NAME%'"

rmdir /s /q "%DIST_DIR%"

echo.
echo ZIP creado en tu Escritorio:
echo   %ZIP_NAME%
echo.
echo Para compartir:
echo   1. Envia el ZIP por correo o USB
echo   2. El destinatario descomprime
echo   3. Abre la carpeta y hace doble clic en INSTALAR.bat
echo.
pause
