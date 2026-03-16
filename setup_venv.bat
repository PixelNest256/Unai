@echo off
chcp 65001 > nul
setlocal

set "PYTHON=C:\Users\Kasam\.pyenv\pyenv-win\versions\3.12.0\python.exe"
set "VENV_DIR=%~dp0.venv"

echo === Unai Virtual Environment Setup ===
echo.

:: Check Python existence
if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    echo Please install Python 3.12.0 using pyenv.
    pause
    exit /b 1
)

:: Create virtual environment (skip if already exists)
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Virtual environment already exists: .venv
) else (
    echo [INFO] Creating virtual environment: .venv
    "%PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
)

:: Upgrade pip
echo.
echo [INFO] Upgrading pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet

:: Install requirements.txt
echo [INFO] Installing dependencies (requirements.txt)...
"%VENV_DIR%\Scripts\pip.exe" install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)
echo [OK] Dependencies installed successfully.

echo.
echo === Setup Complete ===
echo You can run the application with run.bat next time.
echo.
pause
endlocal
