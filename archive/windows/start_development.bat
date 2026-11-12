@echo off
setlocal
set "PROJECT_DIR=D:\Users\admin\Downloads\marathon_training\webgis_for_running"

echo Starting backend and frontend in separate windows...
start "Running WebGIS API" "%PROJECT_DIR%\start_backend_api.bat"
start "Running WebGIS Frontend" "%PROJECT_DIR%\start_frontend.bat"

echo.
echo API docs: http://127.0.0.1:8000/docs
echo The Vite URL will be shown in the frontend window.
echo.
pause
