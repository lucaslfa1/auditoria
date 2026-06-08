@echo off
rem =====================================================================
rem Wrapper Windows para o sync Huawei AICC.
rem Usado pelo Task Scheduler para rodar o sync em horarios fixos.
rem
rem Pre-requisitos:
rem   - Maquina na rede NSTECH (IP whitelisted pela Teledata).
rem   - backend/.env com credenciais Huawei e ENABLE_HUAWEI_SYNC=true.
rem   - Venv em backend\.venv com dependencias instaladas.
rem
rem Configuracao no Task Scheduler:
rem   - Program/script:  C:\Users\lucas.afonso\projetos\auditoria\scripts\huawei_sync.bat
rem   - Start in:        C:\Users\lucas.afonso\projetos\auditoria
rem   - Triggers:        diaria 03:00 (ou a cada N horas)
rem   - Run whether user is logged on or not (recomendado)
rem =====================================================================

setlocal

rem Descobre a raiz do repo (pasta pai de scripts\).
set "REPO_DIR=%~dp0.."
pushd "%REPO_DIR%" >nul

set "BACKEND_DIR=%REPO_DIR%\backend"
set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERRO] Venv nao encontrado em %VENV_PY%.
    echo Rode:  python -m venv backend\.venv ^&^& backend\.venv\Scripts\pip install -r backend\requirements.txt
    popd >nul
    exit /b 2
)

cd /d "%BACKEND_DIR%"
"%VENV_PY%" scripts\run_huawei_sync.py %*
set EXITCODE=%ERRORLEVEL%

popd >nul
endlocal & exit /b %EXITCODE%
