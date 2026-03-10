@echo off
setlocal
chcp 65001 >nul

echo =======================================================
echo     Building Sequential Selector Standalone EXE
echo =======================================================
echo.

set "PYTHON=python"

REM Check Python
%PYTHON% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please add Python to PATH.
    pause
    exit /b 1
)

echo [INFO] Upgrading pip and installing dependencies...
%PYTHON% -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

%PYTHON% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

%PYTHON% -m pip install --upgrade pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

REM Clean previous build
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM Run Build (curated spec with heavy-module excludes for smaller package size)
echo [INFO] Running PyInstaller with ssc.spec...
echo This process may take a few minutes.
echo.

%PYTHON% -m PyInstaller --noconfirm --clean ssc.spec
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

if not exist "dist\SequentialSelector.exe" (
    echo [ERROR] Build output not found: dist\SequentialSelector.exe
    pause
    exit /b 1
)

echo [INFO] Validating artifact size limit (2.0 GiB)...
%PYTHON% scripts\check_artifact_size.py "dist\SequentialSelector.exe" --max-gib 2.0
if %errorlevel% neq 0 (
    echo [ERROR] Artifact exceeded size budget.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo     BUILD SUCCESSFUL
echo =======================================================
echo Output: dist\SequentialSelector.exe
echo.
pause
