@echo off
setlocal
title Running WebGIS Spring Boot API

set "PROJECT_DIR=%~dp0"
set "API_DIR=%PROJECT_DIR%backend_springboot\api"
set "JAVA_HOME=C:\Users\admin\.jdks\openjdk-25\jdk-25.0.2"
set "RUNNING_WEBGIS_DATA_DIR=%PROJECT_DIR%data\processed"

if not exist "%JAVA_HOME%\bin\java.exe" goto :missing_java
if not exist "%API_DIR%\mvnw.cmd" goto :missing_project

set "PATH=%JAVA_HOME%\bin;%PATH%"
cd /d "%API_DIR%"

echo.
echo Starting Running WebGIS Spring Boot API...
echo Java runtime: %JAVA_HOME%
echo Data directory: %RUNNING_WEBGIS_DATA_DIR%
echo API health: http://127.0.0.1:8080/api/health
echo Actuator health: http://127.0.0.1:8080/actuator/health
echo Press Ctrl+C to stop the server.
echo.

call mvnw.cmd spring-boot:run
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Spring Boot stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:missing_java
echo ERROR: JDK 25 was not found.
echo Expected: %JAVA_HOME%\bin\java.exe
pause
exit /b 1

:missing_project
echo ERROR: Maven Wrapper was not found.
echo Expected: %API_DIR%\mvnw.cmd
pause
exit /b 1
