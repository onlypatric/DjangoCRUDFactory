@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

set "PYTHON_BIN=%ROOT_DIR%\.venv\Scripts\python.exe"
set "HOST=localhost"
if "%CRUDFACTORY_DEMO_PORT%"=="" (
  set "PORT=8765"
) else (
  set "PORT=%CRUDFACTORY_DEMO_PORT%"
)
set "BASE_URL=http://%HOST%:%PORT%"
set "OUTPUT_DIR=%ROOT_DIR%\demo_output"
set "LOG_FILE=%OUTPUT_DIR%\server.log"

set "DJANGO_SETTINGS_MODULE=tests.django_project.settings"
if defined PYTHONPATH (
  set "PYTHONPATH=%ROOT_DIR%\src;%ROOT_DIR%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%ROOT_DIR%\src;%ROOT_DIR%"
)

if not exist "%PYTHON_BIN%" (
  echo Expected virtualenv python at %PYTHON_BIN% 1>&2
  echo Create/install the environment first, then rerun this script. 1>&2
  exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo Applying migrations to the demo SQLite database...
"%PYTHON_BIN%" -m django migrate --noinput || exit /b 1

echo Resetting demo database for deterministic output...
"%PYTHON_BIN%" -m django flush --noinput || exit /b 1

echo Starting Django server on %BASE_URL%...
start "crudfactory-demo-server" /b cmd /c ""%PYTHON_BIN%" "%ROOT_DIR%\scripts\crudfactory_demo_server.py" --host "%HOST%" --port "%PORT%" > "%LOG_FILE%" 2>&1"

echo Waiting for Django server...
"%PYTHON_BIN%" -c "from __future__ import annotations; import os, sys, time; from urllib.error import HTTPError, URLError; from urllib.request import Request, urlopen; base_url=f'http://localhost:{os.environ.get(\"CRUDFACTORY_DEMO_PORT\", \"8765\")}'; deadline=time.monotonic()+20; ready=False
while time.monotonic() < deadline:
    try:
        request=Request(f'{base_url}/api/locations/')
        with urlopen(request, timeout=1) as response:
            if response.status < 500:
                ready=True
                break
    except HTTPError as exc:
        if exc.code < 500:
            ready=True
            break
    except URLError:
        time.sleep(0.25)
if not ready:
    print(f'Django server did not become ready at {base_url}', file=sys.stderr)
    sys.exit(1)" || exit /b 1

echo Running demo client and exporting JSON...
"%PYTHON_BIN%" "%ROOT_DIR%\scripts\crudfactory_demo_client.py" --base-url "%BASE_URL%" --output-dir "%OUTPUT_DIR%" || exit /b 1

echo Demo complete.
echo Combined JSON: %OUTPUT_DIR%\crudfactory_demo_results.json
echo Individual responses: %OUTPUT_DIR%\responses\
echo OpenAPI JSON: %OUTPUT_DIR%\ev_openapi_schema.json
echo OpenAPI summary: %ROOT_DIR%\wiki\generated\ev_openapi_summary.md
echo Server log: %LOG_FILE%
