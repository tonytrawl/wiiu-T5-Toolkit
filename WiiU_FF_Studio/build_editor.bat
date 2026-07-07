@echo off
REM ===========================================================================
REM  Wii U FF Editor - build the standalone editor EXE with PyInstaller.
REM  Output: dist\WiiU_FF_Editor.exe
REM ===========================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Wii U FF Editor - release build ===
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python not found on PATH. Install Python 3.9+ and try again.
    pause
    exit /b 1
)

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 ( echo [!] Failed to install PyInstaller. & pause & exit /b 1 )
)

if exist build rmdir /s /q build
if exist WiiU_FF_Editor.spec del /q WiiU_FF_Editor.spec

taskkill /f /im WiiU_FF_Editor.exe >nul 2>nul

echo [*] Building EXE...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name WiiU_FF_Editor ^
    --icon editor.ico ^
    --add-data "wiiu_ff.py;." ^
    --add-data "salsa20.py;." ^
    --add-data "ff_assets.py;." ^
    --add-data "editor.ico;." ^
    --hidden-import wiiu_ff ^
    --hidden-import salsa20 ^
    --hidden-import ff_assets ^
    wiiu_ff_editor.py

if errorlevel 1 ( echo. & echo [!] Build failed - see output above. & pause & exit /b 1 )

echo.
echo === Done. ===
echo     EXE:  dist\WiiU_FF_Editor.exe
echo.
pause
