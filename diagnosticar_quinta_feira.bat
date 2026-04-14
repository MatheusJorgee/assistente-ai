@echo off
REM ============================================================================
REM QUINTA FEIRA - DIAGNÓSTICO RÁPIDO
REM Verifica se tudo está funcionando corretamente
REM ============================================================================

setlocal enabledelayedexpansion

cls
color 0A
echo.
echo ============================================================================
echo  QUINTA-FEIRA - DIAGNÓSTICO RÁPIDO
echo ============================================================================
echo.

set PROJECT_ROOT=C:\Users\mathe\Documents\assistente-ai

REM 1. PYTHON
echo [1/6] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ❌ Python não encontrado!
    goto erro
)
echo ✅ Python OK
echo.

REM 2. VENV
echo [2/6] Verificando Virtual Environment...
if not exist "%PROJECT_ROOT%\.venv" (
    color 0C
    echo ❌ .venv não encontrado!
    goto erro
)
echo ✅ .venv OK
echo.

REM 3. DEPENDÊNCIAS
echo [3/6] Verificando dependências backend...
cd /d "%PROJECT_ROOT%\backend"
.\.venv\Scripts\python -c "import fastapi, uvicorn, google.generativeai" >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ❌ Dependências backend ausentes!
    goto erro
)
echo ✅ Dependências backend OK
echo.

REM 4. BRAIN
echo [4/6] Testando Brain (importação)...
.\.venv\Scripts\python -c "from brain import QuintaFeiraBrain; print('OK')" >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ❌ Brain não está carregando!
    goto erro
)
echo ✅ Brain OK
echo.

REM 5. MAIN
echo [5/6] Verificando main.py...
.\.venv\Scripts\python -c "from main import app; print('OK')" >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ❌ main.py não carrega!
    goto erro
)
echo ✅ main.py OK
echo.

REM 6. FRONTEND
echo [6/6] Verificando Frontend...
cd /d "%PROJECT_ROOT%\frontend"
if not exist "node_modules" (
    color 0E
    echo ⚠️  node_modules não encontrado (será instalado na primeira execução)
) else (
    echo ✅ Frontend OK
)
echo.

color 0A
echo ============================================================================
echo ✅ DIAGNÓSTICO COMPLETO - TUDO OK!
echo ============================================================================
echo.
echo Você pode iniciar com:
echo   1. iniciar_quinta_feira_visivel.bat (recomendado)
echo   2. iniciar_quinta_feira_visivel.ps1 (PowerShell)
echo   3. start.ps1 (script padrão)
echo.
pause
exit /b 0

:erro
echo.
echo ============================================================================
echo ❌ ERRO ENCONTRADO - Solução:
echo ============================================================================
echo.
echo 1. Abra PowerShell como ADMINISTRADOR
echo 2. Execute: cd C:\Users\mathe\Documents\assistente-ai
echo 3. Execute: python -m venv .venv
echo 4. Execute: .\.venv\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1
