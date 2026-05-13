@echo off
setlocal

set "ROOT=%~dp0"

REM ── 1. npm install ────────────────────────────────────────────────────────────
if not exist "%ROOT%client\node_modules\.bin\electron.cmd" (
  echo [INFO] node_modules not found. Running npm install...
  cd /d "%ROOT%client"
  call npm install --include=dev
  if errorlevel 1 (
    echo [ERROR] npm install failed. Check Node.js is installed and try again.
    pause
    endlocal
    exit /b 1
  )
  cd /d "%ROOT%"
)

REM ── 2. Launch the Electron client ────────────────────────────────────────────
start "FederHub Client" cmd /k "cd /d ""%ROOT%client"" && npm start"

echo FederHub client launched in a separate terminal.
pause
endlocal
