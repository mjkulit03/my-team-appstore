@echo off
echo Stopping My Team Platform...
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    echo Found process %%a using port 8000
    taskkill /PID %%a /F >nul 2>&1
    echo Killed process %%a
)

if %ERRORLEVEL% NEQ 0 (
    echo No process found on port 8000, or process already stopped.
) else (
    echo Server stopped successfully.
)
echo.