@echo off
setlocal
title Running WebGIS Frontend

set "PROJECT_DIR=D:\Users\admin\Downloads\marathon_training\webgis_for_running"
cd /d "%PROJECT_DIR%\frontend"

echo.
echo Starting Vite development server...
echo.
npm run dev
pause
