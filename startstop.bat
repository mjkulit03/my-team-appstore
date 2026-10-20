@echo off
if "%1"=="" (
    echo Usage: startstop.bat [start|stop]
    echo.
    echo   start  Start the My Team Platform server
    echo   stop   Stop the My Team Platform server
    exit /b
)

if "%1"=="start" (
    call start.bat
    exit /b
)

if "%1"=="stop" (
    call stop.bat
    exit /b
)

echo Unknown option: %1
echo Usage: startstop.bat [start|stop]