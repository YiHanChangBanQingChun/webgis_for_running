@echo off
setlocal
title Running WebGIS - Spring Boot Development

set "PROJECT_DIR=%~dp0"
set "BACKEND_SCRIPT=%PROJECT_DIR%start_springboot_api.bat"
set "FRONTEND_SCRIPT=%PROJECT_DIR%start_frontend_springboot.bat"

if not exist "%BACKEND_SCRIPT%" goto :missing_backend
if not exist "%FRONTEND_SCRIPT%" goto :missing_frontend

echo Starting Spring Boot API and Vite frontend in separate windows...
start "Running WebGIS Spring Boot API" cmd /c call "%BACKEND_SCRIPT%"
start "Running WebGIS Frontend" cmd /c call "%FRONTEND_SCRIPT%"

echo.
echo Spring Boot API: http://127.0.0.1:8080/api/health
echo Frontend: the Vite URL shown in the frontend window
echo.
echo Close this window or press any key. The two development servers will keep running.
pause >nul
exit /b 0

:missing_backend
echo ERROR: Backend launcher was not found.
echo Expected: %BACKEND_SCRIPT%
pause
exit /b 1

:missing_frontend
echo ERROR: Frontend launcher was not found.
echo Expected: %FRONTEND_SCRIPT%
pause
exit /b 1
