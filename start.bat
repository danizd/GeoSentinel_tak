@echo off
rem ============================================================
rem  GeoSentinel_tak - arranque del simulador CoT en el PC
rem
rem  Uso:
rem    start.bat                          -> fts.movilab.es:8087
rem    start.bat fts.movilab.es           -> host dado, puerto 8087
rem    start.bat 192.168.1.50 8087        -> host y puerto dados
rem
rem  Fase humo (ADR 0002): canal CoT claro 8087. Para la fase de
rem  produccion (8089 TLS) usa WinTAK enrolado por data package;
rem  el simulador en el servidor corre con:
rem    docker compose --profile sim up -d
rem ============================================================
setlocal

set "FTS_HOST=%~1"
set "FTS_PORT=%~2"

if "%FTS_HOST%"=="" set "FTS_HOST=fts.movilab.es"
if "%FTS_PORT%"=="" set "FTS_PORT=8087"

echo ==============================================
echo  GeoSentinel_tak - simulador CoT
echo  Destino : %FTS_HOST%:%FTS_PORT%
echo ==============================================

rem --- localizar Python (py launcher o python en PATH) ---
set "PYEXE="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py -3"
) else (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)
if "%PYEXE%"=="" (
    echo [ERROR] Python 3 no encontrado. Instala Python 3.11+ desde python.org
    echo         o usa el servicio de compose en el servidor:
    echo         docker compose --profile sim up -d
    pause
    exit /b 1
)

rem --- pre-chequeo de conectividad TCP (fase humo) ---
echo Comprobando conectividad TCP a %FTS_HOST%:%FTS_PORT% ...
%PYEXE% -c "import socket,sys;c=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=8);c.close()" %FTS_HOST% %FTS_PORT%
if errorlevel 1 (
    echo [ERROR] Sin conexion TCP a %FTS_HOST%:%FTS_PORT%.
    echo   - Fase humo: abre 8087/tcp en Oracle Security List hacia TU IP publica
    echo   - Prueba: Test-NetConnection %FTS_HOST% -Port %FTS_PORT%
    echo   - Fase produccion: el canal es 8089 TLS y este script no aplica
    pause
    exit /b 1
)
echo Conectividad OK. Arrancando simulador (Ctrl+C para parar)...

%PYEXE% "%~dp0simulator.py"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [INFO] El simulador termino con codigo %EXITCODE%.
)
pause
exit /b %EXITCODE%
