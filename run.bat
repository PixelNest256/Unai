@echo off
chcp 65001 > nul
setlocal

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found.
    echo Please run setup_venv.bat first.
    pause
    exit /b 1
)


"%VENV_PYTHON%" "%~dp0app.py"

endlocal
