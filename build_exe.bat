@echo off
chcp 65001 >nul
echo =======================================================
echo     Building Sequential Selector Standalone EXE
echo =======================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please add Python to PATH.
    pause
    exit /b
)

REM Install PyInstaller if needed
echo [INFO] Checking/Installing PyInstaller...
pip install pyinstaller pillow-heif --upgrade >nul

REM Clean previous build
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "SequentialSelector.spec" del "SequentialSelector.spec"

REM Run Build
echo [INFO] Running PyInstaller...
echo This process may take a few minutes.
echo.

pyinstaller --noconfirm --onefile --windowed --clean ^
    --name "SequentialSelector" ^
    --icon "sqs.ico" ^
    --add-data "sqs.ico;." ^
    --hidden-import "pillow_heif" ^
    --hidden-import "rawpy" ^
    --hidden-import "PySide6" ^
    run.py

echo.
if %errorlevel% neq 0 (
    echo [ERROR] Build Failed!
    pause
    exit /b
)

echo =======================================================
echo     BUILD SUCCESSFUL!
echo =======================================================
echo Executable is located in the 'dist' folder.
echo.
pause
