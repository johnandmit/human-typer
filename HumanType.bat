@echo off
setlocal
cd /d "%~dp0"

:: 1. If standalone HumanType.exe exists, launch it directly
if exist "%~dp0HumanType.exe" (
    start "" "%~dp0HumanType.exe"
    exit /b 0
)

:: 2. Find Python launcher / executable
set "PY_CMD="

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py"
    goto :CHECK_DEPS
)

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :CHECK_DEPS
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :CHECK_DEPS
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto :CHECK_DEPS
)

echo [ERROR] Python was not found on your system!
echo Please install Python 3 or run the standalone HumanType.exe.
echo.
pause
exit /b 1

:CHECK_DEPS
:: Ensure pynput is installed
%PY_CMD% -c "import pynput" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing required dependency: pynput...
    %PY_CMD% -m pip install pynput
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install pynput. Please check your internet connection or run 'pip install pynput' manually.
        pause
        exit /b 1
    )
)

:: Launch humantype.pyw
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0humantype.pyw"
    exit /b 0
)

if "%PY_CMD%"=="py" (
    start "" py -3 -w "%~dp0humantype.pyw"
    exit /b 0
)

start "" "%PY_CMD%" "%~dp0humantype.pyw"
exit /b 0
