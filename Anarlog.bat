@echo off
REM ============================================================
REM  Anarlog launcher
REM  1) Поднимает Claude->OpenAI шим на 127.0.0.1:8799 (если не запущен)
REM     — нужен для summary/чата (транскрипция whisper работает и без него).
REM  2) Запускает собранное приложение.
REM ============================================================

set "REPO=d:\project\anarlog"
set "SHIM=%REPO%\tools\claude-oai-shim\server.py"
set "APP=%REPO%\apps\desktop\src-tauri\target\release\Anarlog Dev.exe"

REM --- 1) шим: стартуем только если порт 8799 ещё не слушается ---
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 8799 -State Listen -ErrorAction SilentlyContinue)) { Start-Process py -ArgumentList '\"%SHIM%\"' -WindowStyle Hidden }"

REM --- 2) приложение ---
if exist "%APP%" (
  start "" "%APP%"
) else (
  echo Не найден собранный exe: "%APP%"
  echo Сначала собери релиз:  pnpm -F desktop tauri:build
  pause
)
