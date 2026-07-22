# Релизная сборка Толмача (Windows)

Даёт standalone `tolmach-dev.exe`, который запускается без dev-сервера.

## Команда

```bash
cd d:/project/anarlog

# GPU (см. docs/windows-gpu-whisper.md — фича `cuda` включается там же)
export PATH="/c/Program Files/CMake/bin:/c/Program Files/LLVM/bin:/c/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6/bin:$PATH"
export LIBCLANG_PATH="C:\Program Files\LLVM\bin"
export CUDA_PATH="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"
export CUDA_PATH_V12_6="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"

# ОБЯЗАТЕЛЬНО: эти переменные читаются макросом env!() на этапе компиляции.
# В dev-сборке они опциональны, в release — жёстко требуются, и без них
# сборка падает ("environment variable ... not defined at compile time").
export VITE_API_URL="http://localhost:3001"   # облачный API апстрима мы не используем
export APP_VERSION="0.1.0"
export VERGEN_GIT_SHA="$(git rev-parse HEAD)"

pnpm -F desktop exec tauri build --no-bundle
```

Результат: `apps/desktop/src-tauri/target/release/tolmach-dev.exe` (~336 МБ — внутри
whisper.cpp с CUDA-ядрами).

## Почему `--no-bundle`

В `tauri.conf.json` включены `createUpdaterArtifacts: true` и `targets: "all"` —
бандлинг требует ключ подписи обновлений, которого у нас нет, и падает.
`--no-bundle` собирает только exe, без инсталлятора и подписи. Если понадобится
инсталлятор — сначала отключить updater-артефакты или завести ключ подписи.

## Что важно знать

- **Идентификатор `com.hyprnote.dev`** — тот же, что у dev-сборки, поэтому релизный
  exe видит те же данные (сессии, БД, шаблоны) в `%APPDATA%/Roaming/com.hyprnote.dev`.
  Менять идентификатор = потерять доступ к существующим данным.
- **Аналитика**: `POSTHOG_API_KEY` сделан опциональным (`plugins/analytics/src/lib.rs`).
  Нет ключа → телеметрия выключена. Раньше release жёстко требовал ключ.
- **Отладочные аудио-файлы** (`audio_mic.wav` / `audio_spk.wav`) пишутся только в
  debug-сборке — в релизе занимают вдвое меньше места.

## Запуск

`Толмач.bat` в корне репо: поднимает шим `tools/claude-oai-shim/server.py` на
127.0.0.1:8799 (нужен для summary/чата), если он не слушает, и стартует exe.
