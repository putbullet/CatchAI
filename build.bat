@echo off
setlocal
cd /d "%~dp0"
set PYTHON=%~dp0.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo ERROR: Catch virtual environment was not found at .venv\Scripts\python.exe
    exit /b 1
)

if exist build\Catch rmdir /s /q build\Catch
if exist dist\Catch.exe del /q dist\Catch.exe

"%PYTHON%" -m PyInstaller --noconfirm --clean Catch.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)
if not exist dist\Catch.exe (
    echo ERROR: dist\Catch.exe was not created.
    exit /b 1
)

echo Catch build complete: %~dp0dist\Catch.exe
exit /b 0
