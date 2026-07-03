#!/usr/bin/env python3
"""
claude-oai-shim — минимальный OpenAI-совместимый HTTP-фасад над Claude Code CLI.

Зачем: anarlog (ноутпад-AI: enhance/summary/чат) ходит к LLM по HTTP через AI SDK,
а мы хотим гонять это через локальный `claude` CLI (существующая авторизация Claude Code,
без отдельного API-ключа). Этот сервер принимает POST /v1/chat/completions в формате
OpenAI и транслирует в `claude -p --output-format json`.

Запуск:  python server.py            (слушает 127.0.0.1:8799)
В anarlog: Settings -> AI -> LLM -> custom / OpenAI-compatible
           Base URL: http://127.0.0.1:8799/v1
           API key:  любой непустой (напр. "local")
           Model:    алиас/ID модели Claude, напр. "sonnet" или "claude-sonnet-4-6"

Зависимостей нет — только стандартная библиотека Python 3.9+.

ОГРАНИЧЕНИЯ (осознанно, для M0):
- Tool/function-calling НЕ поддерживается (enhance/summary — обычная генерация, им не нужно;
  агентный чат по встрече с инструментами может не работать через этот путь).
- Стриминг эмулируется: полный ответ отдаётся одним SSE-чанком, затем [DONE].
- Использование подписочной авторизации Claude Code как бэкенда приложения — ок для личного
  использования; для «друзей» в объёме держите в уме лимиты/ToS.
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
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
# Дефолтная модель, если запрос не указал вменяемую (экономим на summary — sonnet).
DEFAULT_MODEL = os.environ.get("SHIM_DEFAULT_MODEL", "sonnet")
CALL_TIMEOUT = int(os.environ.get("SHIM_TIMEOUT", "240"))

# Нейтральная рабочая папка, чтобы CLI не подхватывал проектный CLAUDE.md / локальные настройки.
NEUTRAL_CWD = tempfile.mkdtemp(prefix="claude-shim-")


def _extract_text(content):
    """content у OpenAI-сообщения бывает строкой или массивом частей."""
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


def build_prompt(messages):
    """Складываем messages в один промпт: system-блоки сверху, затем диалог."""
    system_parts = []
    convo = []
    for m in messages or []:
        role = m.get("role", "user")
        text = _extract_text(m.get("content"))
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            convo.append("Assistant:\n" + text)
        else:  # user / tool / прочее
            convo.append("User:\n" + text)

    prompt = ""
    if system_parts:
        prompt += "\n\n".join(system_parts).strip() + "\n\n"
    prompt += "\n\n".join(convo).strip()
    return prompt


def pick_model(requested):
    if requested and isinstance(requested, str) and requested.strip():
        return requested.strip()
    return DEFAULT_MODEL


def _claude_cmd(model):
    """Формирует argv для запуска claude. На Windows claude — это .cmd (node-скрипт),
    который CreateProcess напрямую не запускает, поэтому оборачиваем в `cmd /c`."""
    exe = shutil.which(CLAUDE_BIN) or CLAUDE_BIN
    base = [exe, "-p", "--output-format", "json"]
    if model:
        base += ["--model", model]
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c"] + base
    return base


def run_claude(prompt, model):
    """Вызывает claude -p, промпт через stdin. Возвращает (text, usage_dict)."""
    cmd = _claude_cmd(model)
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=NEUTRAL_CWD,
        timeout=CALL_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "claude CLI exit {}: {}".format(proc.returncode, (proc.stderr or "")[:2000])
        )
    data = json.loads(proc.stdout)
    text = data.get("result", "")
    u = data.get("usage", {}) or {}
    usage = {
        "prompt_tokens": u.get("input_tokens", 0),
        "completion_tokens": u.get("output_tokens", 0),
        "total_tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0),
    }
    return text, usage


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
            self._send_json({
                "object": "list",
                "data": [
                    {"id": DEFAULT_MODEL, "object": "model", "owned_by": "claude-cli"},
                ],
            })
            return
        self._send_json({"status": "ok"}, 200)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json({"error": {"message": "not found"}}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            self._send_json({"error": {"message": "bad request: %s" % e}}, 400)
            return

        messages = payload.get("messages", [])
        model = pick_model(payload.get("model"))
        stream = bool(payload.get("stream", False))
        prompt = build_prompt(messages)

        try:
            text, usage = run_claude(prompt, model)
        except Exception as e:
            self.log_message("claude call failed: %s", e)
            self._send_json({"error": {"message": str(e)}}, 502)
            return

        created = int(time.time())
        cmpl_id = "chatcmpl-shim-%d" % created

        if stream:
            self._send_stream(cmpl_id, created, model, text)
        else:
            self._send_json({
                "id": cmpl_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                },
            })

    def _send_stream(self, cmpl_id, created, model, text):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def chunk(delta, finish=None):
            obj = {
                "id": cmpl_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))

        chunk({"role": "assistant"})
        chunk({"content": text})
        chunk({}, finish="stop")
        self.wfile.write(b"data: [DONE]\n\n")


def main():
    print("claude-oai-shim: http://%s:%d/v1  (model default: %s, bin: %s)" % (
        HOST, PORT, DEFAULT_MODEL, shutil.which(CLAUDE_BIN) or CLAUDE_BIN))
    print("neutral cwd:", NEUTRAL_CWD)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
