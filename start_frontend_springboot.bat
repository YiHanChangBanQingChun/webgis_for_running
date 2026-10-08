@echo off
setlocal
title Running WebGIS Frontend - Spring Boot

set "PROJECT_DIR=%~dp0"
set "FRONTEND_DIR=%PROJECT_DIR%frontend"
set "VITE_API_PROXY_TARGET=http://127.0.0.1:8080"

if not exist "%FRONTEND_DIR%\package.json" goto :missing_project
where npm >nul 2>&1
if errorlevel 1 goto :missing_npm

cd /d "%FRONTEND_DIR%"

echo.
echo Starting Vite development server...
echo API proxy target: %VITE_API_PROXY_TARGET%
echo The browser URL will be shown below.
echo Press Ctrl+C to stop the server.
echo.

call npm run dev
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Frontend stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:missing_project
echo ERROR: Frontend package.json was not found.
echo Expected: %FRONTEND_DIR%\package.json
pause
exit /b 1

:missing_npm
echo ERROR: npm was not found in PATH.
pause
exit /b 1
