#!/usr/bin/env python3
"""
ai-cli-shim — минимальный OpenAI-совместимый HTTP-фасад над локальными AI-CLI.

Зачем: anarlog (AI-нотпад: enhance/summary/чат) ходит к LLM по HTTP (OpenAI-формат),
а мы хотим гонять это через УЖЕ УСТАНОВЛЕННЫЙ и авторизованный CLI пользователя —
без отдельного API-ключа. Шим сам определяет, какой AI-CLI есть на машине, и роутит
запрос в него. Так друг с любым из этих CLI получает summary/чат «из коробки»:

  • Claude Code CLI   (`claude`)  — Anthropic
  • OpenAI Codex CLI  (`codex`)   — ChatGPT/GPT
  • Google Gemini CLI (`gemini`)  — Gemini

Приоритет автодетекта: claude → codex → gemini. Принудительно: env SHIM_BACKEND=claude|codex|gemini.

Запуск:  python server.py            (слушает 127.0.0.1:8799)
В anarlog: Settings → AI → LLM → custom / OpenAI-compatible
           Base URL: http://127.0.0.1:8799/v1 ; API key: любой непустой ; Model: любой.

Зависимостей нет — только стандартная библиотека Python 3.9+.

ОГРАНИЧЕНИЯ (осознанно): tool-calling не поддерживается (summary/enhance не нужен);
стриминг эмулируется (полный ответ одним SSE-чанком + [DONE]). Использование подписочной
авторизации CLI как бэкенда — на усмотрение владельца CLI (лимиты/ToS).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("SHIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHIM_PORT", "8799"))
CALL_TIMEOUT = int(os.environ.get("SHIM_TIMEOUT", "240"))
FORCED_BACKEND = os.environ.get("SHIM_BACKEND", "").strip().lower()

# Нейтральная рабочая папка, чтобы CLI не подхватывал проектный CLAUDE.md/AGENTS.md/локальные настройки.
NEUTRAL_CWD = tempfile.mkdtemp(prefix="ai-cli-shim-")


# ---------------------------------------------------------------------------
# Разбор OpenAI-запроса
# ---------------------------------------------------------------------------

def _extract_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                parts.append(p.get("text") or p.get("content") or "")
            else:
                parts.append(str(p))
        return "".join(parts)
    return str(content)


def split_messages(messages):
    """→ (system_text, conversation_text)."""
    system_parts, convo = [], []
    for m in messages or []:
        role = m.get("role", "user")
        text = _extract_text(m.get("content"))
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            convo.append("Assistant:\n" + text)
        else:
            convo.append("User:\n" + text)
    return "\n\n".join(system_parts).strip(), "\n\n".join(convo).strip()


def _combined_prompt(system_text, convo_text):
    """Для CLI без отдельного системного промпта — system идёт преамбулой."""
    if system_text and convo_text:
        return system_text + "\n\n---\n\n" + convo_text
    return system_text or convo_text


def _run(cmd, stdin_text):
    """Запуск CLI. На Windows .cmd/.bat оборачиваем в `cmd /c`."""
    if os.name == "nt" and isinstance(cmd[0], str) and cmd[0].lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c"] + cmd
    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=NEUTRAL_CWD,
        timeout=CALL_TIMEOUT,
    )


def _zero_usage():
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# ---------------------------------------------------------------------------
# Бэкенды: (name, bin) + run(system_text, convo_text) -> (text, usage)
# ---------------------------------------------------------------------------

def run_claude(bin_path, system_text, convo_text):
    cmd = [bin_path, "-p", "--output-format", "json"]
    if system_text:
        cmd += ["--system-prompt", system_text]
    proc = _run(cmd, convo_text or " ")
    if proc.returncode != 0:
        raise RuntimeError("claude exit %s: %s" % (proc.returncode, (proc.stderr or "")[:1500]))
    data = json.loads(proc.stdout)
    u = data.get("usage", {}) or {}
    usage = {
        "prompt_tokens": u.get("input_tokens", 0),
        "completion_tokens": u.get("output_tokens", 0),
        "total_tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0),
    }
    return data.get("result", ""), usage


def run_codex(bin_path, system_text, convo_text):
    # `codex exec` читает промпт со stdin; финальный ответ агента пишем в файл
    # через --output-last-message, чтобы не парсить логи/JSONL.
    out_file = os.path.join(NEUTRAL_CWD, "codex_last_%d.txt" % int(time.time() * 1000))
    cmd = [
        bin_path, "exec",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--color", "never",
        "-o", out_file,
        "-",
    ]
    proc = _run(cmd, _combined_prompt(system_text, convo_text))
    if proc.returncode != 0:
        raise RuntimeError("codex exit %s: %s" % (proc.returncode, (proc.stderr or "")[:1500]))
    text = ""
    try:
        with open(out_file, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
    except OSError:
        pass
    if not text:
        # запасной путь: последняя непустая строка stdout
        text = "\n".join(l for l in (proc.stdout or "").splitlines() if l.strip()).strip()
    return text, _zero_usage()


_GEMINI_NOISE = (
    "loaded cached credentials",
    "deprecationwarning",
    "(node:",
    "(use `node",
    "data collection is disabled",
)


def _clean_gemini(out):
    """Gemini CLI печатает служебные строки (creds/node-warnings) в stdout — вырезаем их."""
    kept = [
        line for line in (out or "").splitlines()
        if line.strip() and not any(n in line.lower() for n in _GEMINI_NOISE)
    ]
    return "\n".join(kept).strip()


def run_gemini(bin_path, system_text, convo_text):
    # `-p` включает non-interactive. Роль-лейблы ("User:\n") убираем — gemini это
    # обычный prompt-CLI, а не агент, и лейблы сбивают его с толку.
    convo = convo_text.replace("User:\n", "").replace("Assistant:\n", "")
    prompt = _combined_prompt(system_text, convo)
    cmd = [bin_path, "-p", prompt]
    proc = _run(cmd, "")
    if proc.returncode != 0:
        raise RuntimeError("gemini exit %s: %s" % (proc.returncode, (proc.stderr or "")[:1500]))
    return _clean_gemini(proc.stdout), _zero_usage()


BACKENDS = [
    ("claude", run_claude),
    ("codex", run_codex),
    ("gemini", run_gemini),
]


def detect_backend():
    """Возвращает (name, bin_path, runner) или (None, None, None)."""
    order = BACKENDS
    if FORCED_BACKEND:
        order = [b for b in BACKENDS if b[0] == FORCED_BACKEND] or BACKENDS
    for name, runner in order:
        path = shutil.which(name)
        if path:
            return name, path, runner
    return None, None, None


ACTIVE_NAME, ACTIVE_BIN, ACTIVE_RUN = detect_backend()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[shim] " + (fmt % args) + "\n")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            model_id = ACTIVE_NAME or "none"
            self._send_json({
                "object": "list",
                "data": [{"id": model_id, "object": "model", "owned_by": ACTIVE_NAME or "none"}],
            })
            return
        self._send_json({"status": "ok", "backend": ACTIVE_NAME})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json({"error": {"message": "not found"}}, 404)
            return
        if not ACTIVE_RUN:
            self._send_json({"error": {"message": "no AI CLI detected (claude/codex/gemini)"}}, 503)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            self._send_json({"error": {"message": "bad request: %s" % e}}, 400)
            return

        model = payload.get("model") or ACTIVE_NAME
        stream = bool(payload.get("stream", False))
        system_text, convo_text = split_messages(payload.get("messages", []))

        try:
            text, usage = ACTIVE_RUN(ACTIVE_BIN, system_text, convo_text)
        except Exception as e:
            self.log_message("%s call failed: %s", ACTIVE_NAME, e)
            self._send_json({"error": {"message": str(e)}}, 502)
            return

        created = int(time.time())
        cmpl_id = "chatcmpl-shim-%d" % created

        if stream:
            self._send_stream(cmpl_id, created, model, text, usage)
        else:
            self._send_json({
                "id": cmpl_id, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": usage,
            })

    def _send_stream(self, cmpl_id, created, model, text, usage):
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def chunk(delta, finish=None, extra=None):
            obj = {
                "id": cmpl_id, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if extra:
                obj.update(extra)
            self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))

        chunk({"role": "assistant"})
        chunk({"content": text})
        chunk({}, finish="stop", extra={"usage": usage})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    if ACTIVE_NAME:
        print("ai-cli-shim: http://%s:%d/v1  backend=%s (%s)" % (HOST, PORT, ACTIVE_NAME, ACTIVE_BIN))
    else:
        print("ai-cli-shim: http://%s:%d/v1  WARNING: no AI CLI found (claude/codex/gemini)" % (HOST, PORT))
    print("neutral cwd:", NEUTRAL_CWD)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
