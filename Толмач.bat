@echo off
REM ============================================================
REM  Tolmach launcher
REM  1) Starts the Claude->OpenAI shim on 127.0.0.1:8799 if it is
REM     not already listening. Needed for summary/chat; local
REM     Whisper transcription works without it.
REM  2) Starts the built Tolmach executable.
REM
REM  Build the exe first (once, or after code changes):
REM     pnpm -F desktop exec tauri build --no-bundle
REM ============================================================

set "REPO=d:\project\anarlog"
set "SHIM=%REPO%\tools\claude-oai-shim\server.py"
set "APP=%REPO%\apps\desktop\src-tauri\target\release\tolmach-dev.exe"

REM --- 1) shim: start only if port 8799 is not listening ---
powershell -NoProfile -Command ^
  "if (-not (Get-NetTCPConnection -LocalPort 8799 -State Listen -ErrorAction SilentlyContinue)) { Start-Process py -ArgumentList '\"%SHIM%\"' -WindowStyle Hidden }"

REM --- 2) app ---
if exist "%APP%" (
  start "" "%APP%"
) else (
  echo.
  echo Executable not found:
  echo   "%APP%"
  echo.
  echo Build it first:
  echo   cd /d "%REPO%"
  echo   pnpm -F desktop exec tauri build --no-bundle
  echo.
  pause
)
