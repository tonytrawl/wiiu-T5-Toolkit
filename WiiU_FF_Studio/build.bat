@echo off
REM ===========================================================================
REM  Wii U Fastfile Studio - build a standalone Windows EXE with PyInstaller.
REM  Output: dist\WiiU_FF_Studio.exe
REM ===========================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Wii U Fastfile Studio - release build ===
echo.

REM --- find python -----------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python not found on PATH. Install Python 3.9+ and try again.
    pause
    exit /b 1
)

REM --- ensure pyinstaller -----------------------------------------------------
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [!] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

REM --- clean previous build ---------------------------------------------------
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist WiiU_FF_Studio.spec del /q WiiU_FF_Studio.spec

REM --- close any running copy so the EXE isn't locked -------------------------
taskkill /f /im WiiU_FF_Studio.exe >nul 2>nul

REM --- build ------------------------------------------------------------------
echo [*] Building EXE...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name WiiU_FF_Studio ^
    --icon studio.ico ^
    --add-data "wiiu_ff.py;." ^
    --add-data "salsa20.py;." ^
    --add-data "zone_validate.py;." ^
    --add-data "ff_assets.py;." ^
    --add-data "studio.ico;." ^
    --hidden-import wiiu_ff ^
    --hidden-import salsa20 ^
    --hidden-import zone_validate ^
    --hidden-import ff_assets ^
    wiiu_ff_studio.py

if errorlevel 1 (
    echo.
    echo [!] Build failed - see the PyInstaller output above.
    pause
    exit /b 1
)

echo.
echo === Done. ===
echo     EXE:  dist\WiiU_FF_Studio.exe
echo     Ship it with README.md, USAGE.md, and (optional) oat\Unlinker.exe
echo.
pause
