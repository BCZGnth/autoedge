@echo off
setlocal enabledelayedexpansion

rem --- Locate conda -----------------------------------------------------
set "CONDA_BAT="
for %%P in (
    "C:\ProgramData\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%USERPROFILE%\AppData\Local\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\AppData\Local\conda\condabin\conda.bat"
) do (
    if exist %%P set "CONDA_BAT=%%~P"
)

if not defined CONDA_BAT (
    echo [!] Could not find conda.bat in any of the usual locations.
    echo     Edit setup_autoedge.bat and set CONDA_BAT to your conda install.
    pause
    exit /b 1
)

echo [*] Using conda at "%CONDA_BAT%"

rem --- Create the env if it doesn't exist yet ----------------------------
call "%CONDA_BAT%" env list | findstr /r /c:"^autoedge " >nul
if errorlevel 1 (
    echo [*] Creating conda environment "autoedge" with Python 3.11...
    call "%CONDA_BAT%" create -n autoedge python=3.11 -y
    if errorlevel 1 (
        echo [!] Failed to create the conda environment.
        pause
        exit /b 1
    )
) else (
    echo [*] Conda environment "autoedge" already exists.
)

rem --- Install / update dependencies -------------------------------------
echo [*] Installing selenium into "autoedge"...
call "%CONDA_BAT%" run -n autoedge pip install --upgrade selenium
if errorlevel 1 (
    echo [!] Failed to install selenium.
    pause
    exit /b 1
)

echo.
echo [+] Setup complete. Run run_autoedge.bat to start the script.
pause
