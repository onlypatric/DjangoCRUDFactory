@echo off
setlocal

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"
set "VENV_DIR=%ROOT_DIR%\.venv"

where "%PYTHON_BIN%" >nul 2>nul
if errorlevel 1 (
  echo Could not find Python interpreter: %PYTHON_BIN% 1>&2
  echo Set PYTHON_BIN to a Python 3.12+ executable and rerun. 1>&2
  exit /b 1
)

echo Creating virtualenv at %VENV_DIR%...
"%PYTHON_BIN%" -m venv "%VENV_DIR%" || exit /b 1

echo Upgrading pip, setuptools, and wheel...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel || exit /b 1

echo Installing crudfactory with dev extras...
"%VENV_DIR%\Scripts\python.exe" -m pip install -e "%ROOT_DIR%[dev]" || exit /b 1

echo Virtualenv ready.
echo Activate with: %VENV_DIR%\Scripts\activate.bat
