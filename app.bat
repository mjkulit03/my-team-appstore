@echo off
setlocal enabledelayedexpansion

if "%1"=="" (
    echo My Team Platform Management
    echo.
    echo Usage: app.bat [start^|stop^|restart^|status]
    echo.
    echo   start    - Start the development server (with auto-reload)
    echo   stop     - Stop the server
    echo   restart  - Restart the server
    echo   status   - Check if server is running
    echo.
    goto :end
)

if "%1"=="start" (
    echo Starting My Team Platform...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
        echo Server is already running (PID: %%a)
        echo Use 'app.bat stop' to stop it first.
        goto :end
    )
    start "" cmd /c "uvicorn main:app --reload --port 8000"
    echo Server started in new window.
    echo Access at: http://127.0.0.1:8000/
    goto :end
)

if "%1"=="stop" (
    echo Stopping My Team Platform...
    set found=0
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
        echo Found process %%a using port 8000
        taskkill /PID %%a /F >nul 2>&1
        echo Killed process %%a
        set found=1
    )
    if !found! == 0 (
        echo No process found on port 8000.
    ) else (
        echo Server stopped.
    )
    goto :end
)

if "%1"=="restart" (
    call :stop
    timeout /t 2 /nobreak >nul
    call :start
    goto :end
)

if "%1"=="status" (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
        echo Server is running (PID: %%a) on port 8000
        goto :end
    )
    echo Server is not running.
    goto :end
)

echo Unknown command: %1
echo Use 'app.bat' for help.

:end
endlocal

:stop
echo Stopping My Team Platform...
set found=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    taskkill /PID %%a /F >nul 2>&1
    set found=1
)
goto :eof

:start
start "" cmd /c "uvicorn main:app --reload --port 8000"
echo Server started.
goto :eof