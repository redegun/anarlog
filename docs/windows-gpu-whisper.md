# Windows: GPU-ускорение локального Whisper (CUDA)

По умолчанию desktop собирается с CPU-whisper.cpp (`features = ["whisper-cpp"]` у
`tauri-plugin-local-stt`). Пост-обработка часовой встречи на CPU занимает много минут.
На машине с NVIDIA GPU whisper.cpp можно собрать с CUDA — расшифровка идёт в разы
быстрее реального времени (на RTX 4090 ~real-time factor 0.03).

Это **машинно-зависимая** сборка (нужен CUDA Toolkit), поэтому фича `cuda` намеренно
НЕ включена в коммит — включай её локально по инструкции ниже.

## Предпосылки

1. **NVIDIA-драйвер** задаёт потолок версии CUDA. Проверь: `nvidia-smi` → строка
   `CUDA Version: X.Y`. Ставить Toolkit можно не новее этого потолка **без** обновления
   драйвера (напр. драйвер 566.x → CUDA ≤ 12.7 → ставим Toolkit 12.6).
2. **Совместимость CUDA ↔ MSVC.** Старый Toolkit не поддерживает свежий MSVC:
   CUDA 12.0 не собирается с MSVC 19.44 (VS 2022 17.14) — падает `No CUDA toolset found`
   или ошибка идентификации CUDA-компилятора. Бери Toolkit, чей релиз новее твоего MSVC
   (для VS 2022 17.14 — CUDA 12.6+).
3. При установке Toolkit включи компонент **Visual Studio Integration** — он кладёт
   `CUDA <ver>.props/.targets` в
   `…\Microsoft Visual Studio\2022\<Edition>\MSBuild\Microsoft\VC\v170\BuildCustomizations\`.
   Установщик иногда пропускает **Build Tools** (интегрируется только с полной VS) — тогда
   скопируй файлы вручную из
   `…\NVIDIA GPU Computing Toolkit\CUDA\v<ver>\extras\visual_studio_integration\MSBuildExtensions\`
   в BuildCustomizations (нужны права администратора).

## Включение

1. В `apps/desktop/src-tauri/Cargo.toml` добавь фичу `cuda`:
   ```toml
   tauri-plugin-local-stt = { workspace = true, features = ["whisper-cpp", "cuda"] }
   ```
2. Убедись, что окружение сборки видит нужную версию Toolkit (важно для MSBuild-таргетов):
   ```bash
   export PATH="/c/Program Files/CMake/bin:/c/Program Files/LLVM/bin:/c/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6/bin:$PATH"
   export LIBCLANG_PATH="C:\Program Files\LLVM\bin"
   export CUDA_PATH="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"
   export CUDA_PATH_V12_6="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"
   ```
   `CUDA_PATH_V12_6` обязателен: MSBuild-таргеты CUDA резолвят каталог Toolkit именно из
   `CUDA_PATH_V<major>_<minor>`; без неё configure падает с
   `The CUDA Toolkit v12.6 directory '' does not exist`.
3. Если раньше был неудачный CUDA-конфиг — почисти кэш cmake перед сборкой:
   ```bash
   rm -rf apps/desktop/src-tauri/target/debug/build/whisper-rs-sys-*
   ```
4. Собери/запусти как обычно: `pnpm -F desktop tauri:dev` (первая CUDA-сборка дольше —
   компилятся GPU-ядра; дальше из кэша).

Проверка, что GPU реально используется: при расшифровке в логе `transcribe_completed` для
кусков в несколько секунд аудио приходит за ~100 мс (на CPU — секунды).
