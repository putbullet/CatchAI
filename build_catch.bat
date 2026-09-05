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

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$desktop = [Environment]::GetFolderPath('Desktop'); $shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Catch.lnk')); $shortcut.TargetPath = (Join-Path (Get-Location) 'dist\Catch.exe'); $shortcut.WorkingDirectory = (Join-Path (Get-Location) 'dist'); $shortcut.Description = 'Catch local Windows AI assistant'; $shortcut.Save()"
if errorlevel 1 (
    echo WARNING: Catch.exe was built, but the Desktop shortcut could not be created.
    exit /b 0
)

echo Catch build complete: %~dp0dist\Catch.exe
echo Desktop shortcut created: Catch.lnk
exit /b 0
