@echo off
chcp 65001 >nul 2>&1
title Chopo Price Intelligence

cd /d "%~dp0"

REM Abrir el navegador al dashboard
start "" "http://localhost:8501"
timeout /t 2 /nobreak >nul

REM Iniciar el servidor dashboard
call venv\Scripts\python main.py dashboard
