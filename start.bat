@echo off
chcp 65001 > nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYENV_PYTHON=%USERPROFILE%\.pyenv\pyenv-win\versions\3.12.0\python.exe"

if exist "%PYENV_PYTHON%" (
    "%PYENV_PYTHON%" "%SCRIPT_DIR%setup.py"
) else (
    python "%SCRIPT_DIR%setup.py"
)

endlocal