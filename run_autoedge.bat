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
    echo     Run setup_autoedge.bat first, or edit this file to point at your conda install.
    pause
    exit /b 1
)

call "%CONDA_BAT%" activate autoedge
if errorlevel 1 (
    echo [!] Could not activate the "autoedge" conda environment.
    echo     Run setup_autoedge.bat first to create it.
    pause
    exit /b 1
)

python "%~dp0autoedge.py" %*
pause
