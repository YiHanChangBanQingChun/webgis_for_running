@echo off
setlocal
title Running WebGIS API

set "PROJECT_DIR=D:\Users\admin\Downloads\marathon_training\webgis_for_running"
set "CONDA_ACTIVATE=F:\miniconda_new\miniconda_install\Scripts\activate.bat"

if not exist "%CONDA_ACTIVATE%" goto :missing_conda

cd /d "%PROJECT_DIR%"
call "%CONDA_ACTIVATE%" running-webgis

echo.
echo Starting Running WebGIS API...
echo API documentation: http://127.0.0.1:8000/docs
echo Press Ctrl+C to stop the server.
echo.
uvicorn app.main:app --app-dir backend --reload
pause
exit /b

:missing_conda
echo ERROR: Conda activation script was not found.
echo Expected: %CONDA_ACTIVATE%
pause
exit /b 1
