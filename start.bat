@echo off
echo Starting My Team Platform...
echo.
echo Access URLs:
echo   - Storefront: http://127.0.0.1:8000/
echo   - AI Dashboard: http://127.0.0.1:8000/dashboard
echo   - Control Panel: http://127.0.0.1:8000/control/login
echo   - API Docs: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C to stop the server.
echo.

uvicorn main:app --reload --port 8000