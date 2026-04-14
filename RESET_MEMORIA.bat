@echo off
REM Script para reset de memória - Remove o histórico de erros da Quinta-Feira
REM Utilidade para resolver "Alucinação Induzida por Histórico"

cd /d "%~dp0"
echo.
echo ====== RESET DE MEMORIA - QUINTA-FEIRA ======
echo Removendo historico de erros guardados na base de dados...
echo.

python reset_memoria.py

if errorlevel 1 (
    echo.
    echo ERRO: Falha ao executar reset de memoria
    pause
)
