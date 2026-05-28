@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "PYTHON_SCRIPT=%PROJECT_ROOT%scripts\create_island_scene.py"
set "OUTPUT_DIR=%PROJECT_ROOT%output"
set "BLEND_PATH=%OUTPUT_DIR%\island_two_villages.blend"
set "GLB_PATH=%OUTPUT_DIR%\island_two_villages.glb"
set "BLENDER_EXE="

where blender >nul 2>nul
if not errorlevel 1 set "BLENDER_EXE=blender"

if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.4\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
)

if not defined BLENDER_EXE (
    echo Blender was not found. Installing Blender with winget...
    winget install BlenderFoundation.Blender --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Automatic Blender installation failed.
        exit /b 1
    )
)

if not defined BLENDER_EXE (
    where blender >nul 2>nul
    if not errorlevel 1 set "BLENDER_EXE=blender"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.4\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
)
if not defined BLENDER_EXE (
    if exist "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
)

if not defined BLENDER_EXE (
    echo Blender installation completed, but no usable blender executable was found on PATH or in common install paths.
    exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo Using Blender: %BLENDER_EXE%
"%BLENDER_EXE%" --background --python "%PYTHON_SCRIPT%"
if errorlevel 1 (
    echo Blender scene generation failed.
    exit /b 1
)

if not exist "%BLEND_PATH%" (
    echo Expected Blender file was not created: %BLEND_PATH%
    exit /b 1
)

if not exist "%GLB_PATH%" (
    echo Expected GLB preview was not created: %GLB_PATH%
    exit /b 1
)

echo.
echo Generated files:
echo   %BLEND_PATH%
echo   %GLB_PATH%
endlocal
