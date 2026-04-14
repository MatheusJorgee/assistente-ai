@echo off
REM Script para iniciar o backend Quinta-Feira v2.1
REM Uso: execute este arquivo para iniciar o servidor FastAPI

cd /d "%~dp0"
echo.
echo ====== QUINTA-FEIRA v2.1 BACKEND ======
echo Iniciando servidor em http://localhost:8000
echo.

python backend/main.py

if errorlevel 1 (
    echo.
    echo ERRO: Falha ao executar backend
    echo Verifique se Python esta instalado e requirements.txt foi executado
    pause
)
