@echo off
setlocal

set "ROOT=%~dp0"

echo FederHub Windows setup starting from:
echo %ROOT%
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH.
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker was not found in PATH.
  exit /b 1
)

echo [1/6] Installing backend Python dependencies...
cd /d "%ROOT%backend"
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [2/6] Installing federated-engine Python dependencies...
cd /d "%ROOT%federated-engine"
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [3/6] Installing client Python dependencies...
cd /d "%ROOT%client"
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [4/6] Installing frontend Node dependencies...
cd /d "%ROOT%frontend"
call npm install --include=dev
if errorlevel 1 goto :fail

echo.
echo [5/6] Installing client Node dependencies...
cd /d "%ROOT%client"
call npm install --include=dev
if errorlevel 1 goto :fail

echo.
echo [6/6] Building the FederHub client Docker image...
cd /d "%ROOT%"
docker build -t federhub-beta-trainer -f client/Dockerfile .
if errorlevel 1 goto :fail

echo.
echo FederHub Windows setup completed successfully.
echo Next step:
echo   1. run run_all_services_windows.bat
echo   2. run run_client_windows.bat when you want the desktop client
pause
endlocal
exit /b 0

:fail
echo.
echo [ERROR] FederHub Windows setup failed. Review the output above.
pause
endlocal
exit /b 1
