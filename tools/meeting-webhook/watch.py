#!/usr/bin/env python3
"""
meeting-webhook — следит за готовыми заметками anarlog и шлёт задачи/резюме на webhook.

Зачем: P0 из спеки — после встречи action items улетают в твой стек (Telegram/CRM/n8n).
Работает БЕЗ пересборки приложения: anarlog пишет готовую заметку на диск как
`sessions/<id>/_summary.md`, мы за ней следим и POST'им JSON на настраиваемый URL.
Этот же приём переиспользуется для P1 (заливка .md в LightRAG).

Запуск:
  set WEBHOOK_URL=https://your-endpoint/...   (или config.json рядом)
  py watch.py                 # следить в фоне
  py watch.py --once <file>   # разобрать один _summary.md (тест/дебаг)
  py watch.py --dry-run       # следить, но не слать — печатать JSON в консоль

Конфиг (по приоритету): env WEBHOOK_URL  →  config.json {"webhook_url": "..."}.
Заголовки: env WEBHOOK_AUTH → добавляется как "Authorization".
Зависимостей нет — только стандартная библиотека Python 3.9+.
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# Папка данных приложения (тот же профиль, что и dev-сборка).
DEFAULT_SESSIONS = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "com.hyprnote.dev", "sessions",
)
SESSIONS_DIR = os.environ.get("ANARLOG_SESSIONS_DIR", DEFAULT_SESSIONS)
POLL_SECONDS = int(os.environ.get("WEBHOOK_POLL_SECONDS", "5"))

# Заголовки разделов с задачами — рус/англ.
ACTION_HEADING_RE = re.compile(
    r"(action items|to-?do|next steps|задачи|задача|действия|"
    r"следующие шаги|договор|поручени)",
    re.IGNORECASE,
)


def load_webhook_url():
    url = os.environ.get("WEBHOOK_URL", "").strip()
    if url:
        return url
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                return str(json.load(f).get("webhook_url", "")).strip()
        except Exception as e:
            sys.stderr.write("[webhook] bad config.json: %s\n" % e)
    return ""


def parse_frontmatter(text):
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4:].lstrip("\n")
            for line in fm.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    return meta, body


def split_sections(body):
    """H1-секции: возвращает список (heading, [строки-контента])."""
    sections = []
    current = None
    for line in body.splitlines():
        if line.startswith("# "):
            current = (line[2:].strip(), [])
            sections.append(current)
        elif current is not None:
            current[1].append(line)
        else:
            sections.append(("", [line]))  # преамбула до первого H1
            current = None
    return sections


def extract(text):
    meta, body = parse_frontmatter(text)
    sections = split_sections(body)

    # Заголовок: первый H1 или frontmatter title.
    title = ""
    for heading, _ in sections:
        if heading:
            title = heading
            break
    title = title or meta.get("title", "").strip()

    # Задачи: буллеты из секции, чей заголовок похож на "задачи/action items".
    action_items = []
    for heading, lines in sections:
        if heading and ACTION_HEADING_RE.search(heading):
            for ln in lines:
                s = ln.strip()
                if s.startswith(("- ", "* ", "• ")):
                    action_items.append(s[2:].strip())

    return {
        "session_id": meta.get("session_id", ""),
        "note_id": meta.get("id", ""),
        "title": title,
        "action_items": action_items,
        "summary_md": body.strip(),
    }


def post(url, payload, dry_run=False):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run or not url:
        print("[webhook] (dry-run) payload:\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        return
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    auth = os.environ.get("WEBHOOK_AUTH", "").strip()
    if auth:
        req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("[webhook] POST %s -> %s" % (url, resp.status))
    except Exception as e:
        sys.stderr.write("[webhook] POST failed: %s\n" % e)


def process_file(path, url, dry_run, seen):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return
    if not text.strip():
        return
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if seen.get(path) == digest:
        return  # без изменений — не дублируем
    seen[path] = digest
    payload = extract(text)
    payload["_source"] = path
    print("[webhook] note ready: %s (%d action items)" % (
        payload.get("title") or "(без заголовка)", len(payload["action_items"])))
    post(url, payload, dry_run=dry_run)


def watch(url, dry_run):
    print("[webhook] watching %s (poll %ss) -> %s" % (
        SESSIONS_DIR, POLL_SECONDS, url or "(dry-run: URL не задан)"))
    seen = {}
    # первый проход помечаем как виденное, чтобы не слать всю историю на старте
    first = True
    while True:
        try:
            for root, _dirs, files in os.walk(SESSIONS_DIR):
                for name in files:
                    if name == "_summary.md":
                        p = os.path.join(root, name)
                        if first:
                            try:
                                with open(p, encoding="utf-8") as f:
                                    seen[p] = hashlib.sha256(f.read().encode("utf-8")).hexdigest()
                            except Exception:
                                pass
                        else:
                            process_file(p, url, dry_run, seen)
        except Exception as e:
            sys.stderr.write("[webhook] scan error: %s\n" % e)
        first = False
        time.sleep(POLL_SECONDS)


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if "--once" in args:
        i = args.index("--once")
        path = args[i + 1]
        with open(path, encoding="utf-8") as f:
            payload = extract(f.read())
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    watch(load_webhook_url(), dry_run)


if __name__ == "__main__":
    main()
