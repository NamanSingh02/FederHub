@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"

echo Starting FederHub services from:
echo %ROOT%
echo.

start "FederHub Gamma Server" cmd /k "cd /d ""%ROOT%federated-engine"" && python grpc_server.py"
timeout /t 2 /nobreak >nul

start "FederHub Backend" cmd /k "cd /d ""%ROOT%backend"" && python -m uvicorn app.main:app --reload"
timeout /t 2 /nobreak >nul

start "FederHub Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm start"
timeout /t 2 /nobreak >nul

echo.
echo FederHub services were launched in separate terminals:
echo   - Gamma gRPC server
echo   - Backend API
echo   - Frontend
echo.
echo The desktop client is not launched by default.
echo Start it separately with run_client_windows.bat when you want to simulate
echo the real download/install workflow.
echo.
echo If any service fails, check that terminal for dependency or environment errors.

endlocal
