#!/usr/bin/env python3
"""
meeting-webhook — следит за готовыми заметками anarlog и рассылает их по стокам.

Два стока (оба опциональны, работают независимо):
  • P0  webhook   — задачи/резюме встречи POST'ятся JSON'ом на настраиваемый URL
                    (Telegram-бот / CRM / n8n).
  • P1  lightrag  — полный markdown резюме заливается в LightRAG на VPS,
                    чтобы был чат по всей истории встреч (cross-meeting RAG).

Работает БЕЗ пересборки приложения: anarlog пишет готовую заметку на диск как
`sessions/<id>/_summary.md`, мы за ней следим и раздаём по включённым стокам.

Запуск:
  py watch.py                 # следить в фоне (по включённым стокам)
  py watch.py --dry-run       # следить, но не слать — печатать в консоль
  py watch.py --once <file>   # разобрать один _summary.md и напечатать payload (тест)
  py watch.py --push <file>   # разово прогнать один _summary.md по стокам (тест)

Конфиг (по приоритету: env → config.json рядом):
  WEBHOOK_URL / webhook_url            — включает P0. Пусто = сток выключен.
  WEBHOOK_AUTH / webhook_auth          — уходит в заголовок Authorization.
  LIGHTRAG_URL / lightrag_url          — включает P1 (напр. http://127.0.0.1:9621
                                         через ssh-тоннель, см. tunnel.bat).
  LIGHTRAG_API_KEY / lightrag_api_key  — X-API-Key (дефолт — ключ neprosto).
  ANARLOG_SESSIONS_DIR                 — где искать заметки (дефолт — профиль dev).
  WEBHOOK_POLL_SECONDS                 — период опроса (дефолт 5).

Зависимостей нет — только стандартная библиотека Python 3.9+.
"""

import hashlib
import json
import os
import re
import sys
import threading
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
DEFAULT_LIGHTRAG_KEY = "lightrag-neprosto-api-key-2026"

# Заголовки разделов с задачами — рус/англ.
ACTION_HEADING_RE = re.compile(
    r"(action items|to-?do|next steps|задачи|задача|действия|"
    r"следующие шаги|договор|поручени)",
    re.IGNORECASE,
)

# LightRAG-операции сериализуем — параллельные delete/insert конфликтуют в пайплайне.
_LR_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Конфиг
# ---------------------------------------------------------------------------

def _cfg_file():
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write("[cfg] bad config.json: %s\n" % e)
    return {}


def load_config():
    fc = _cfg_file()

    def pick(env_key, cfg_key, default=""):
        v = os.environ.get(env_key, "").strip()
        if v:
            return v
        return str(fc.get(cfg_key, default) or "").strip()

    return {
        "webhook_url": pick("WEBHOOK_URL", "webhook_url"),
        "webhook_auth": pick("WEBHOOK_AUTH", "webhook_auth"),
        "lightrag_url": pick("LIGHTRAG_URL", "lightrag_url"),
        "lightrag_key": pick("LIGHTRAG_API_KEY", "lightrag_api_key", DEFAULT_LIGHTRAG_KEY),
    }


# ---------------------------------------------------------------------------
# Разбор заметки
# ---------------------------------------------------------------------------

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


# Заголовок любого уровня: anarlog штатно шлёт H1, но LLM иногда сбивается на H2/H3.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def split_sections(body):
    """Markdown-секции по заголовку любого уровня: список (heading, [строки-контента])."""
    sections = []
    current = None
    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if m:
            current = (m.group(2).strip(), [])
            sections.append(current)
        elif current is not None:
            current[1].append(line)
        else:
            sections.append(("", [line]))  # преамбула до первого заголовка
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


# ---------------------------------------------------------------------------
# Сток P0: webhook
# ---------------------------------------------------------------------------

def sink_webhook(cfg, payload, dry_run):
    url = cfg["webhook_url"]
    if not url:
        return
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run:
        print("[webhook] (dry-run) payload:\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        return
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg["webhook_auth"]:
        req.add_header("Authorization", cfg["webhook_auth"])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("[webhook] POST %s -> %s" % (url, resp.status))
    except Exception as e:
        sys.stderr.write("[webhook] POST failed: %s\n" % e)


# ---------------------------------------------------------------------------
# Сток P1: LightRAG (cross-meeting RAG)
# ---------------------------------------------------------------------------

def _lr_request(cfg, method, endpoint, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["lightrag_url"].rstrip("/") + endpoint,
        data=data,
        method=method,
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", cfg["lightrag_key"])
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _lr_wait_idle(cfg, label, max_wait=180):
    """Ждём, пока пайплайн освободится. Не блокируем навечно — max_wait секунд."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            body = _lr_request(cfg, "GET", "/documents/pipeline_status", timeout=20)
        except Exception:
            return  # статус недоступен — не блокируем, пробуем как есть
        if not (body.get("busy") or body.get("request_pending")):
            return
        time.sleep(5)
    sys.stderr.write("[lightrag] пайплайн всё ещё занят после %s (%ss), продолжаю\n" % (label, max_wait))


def _lr_find_existing(cfg, file_source):
    """Ищем уже залитые доки этой встречи (по file_path == file_source)."""
    ids, page = [], 1
    while True:
        body = _lr_request(cfg, "POST", "/documents/paginated", {
            "page": page,
            "page_size": 200,
            "sort_field": "updated_at",
            "sort_direction": "desc",
            "status_filter": None,
        }, timeout=60)
        for doc in (body.get("documents") or []):
            if doc.get("file_path") == file_source and doc.get("id"):
                ids.append(doc["id"])
        if not (body.get("pagination") or {}).get("has_next"):
            break
        page += 1
    return ids


def _lr_source_id(payload, src_path):
    """Стабильный идентификатор источника: одна встреча = один doc, переиндексируется при изменении."""
    sid = payload.get("session_id") or payload.get("note_id")
    if not sid:
        sid = hashlib.sha1(os.path.abspath(src_path).encode("utf-8")).hexdigest()[:12]
    return "anarlog-meeting/%s.md" % sid


def _lr_document(payload):
    """Текст для индексации: заголовок-контекст + полное резюме."""
    title = payload.get("title") or "Без заголовка"
    header = "Встреча (заметки Anarlog): %s" % title
    if payload.get("session_id"):
        header += "\nSession: %s" % payload["session_id"]
    return header + "\n\n" + (payload.get("summary_md") or "")


def _push_lightrag(cfg, payload, src_path, dry_run):
    file_source = _lr_source_id(payload, src_path)
    text = _lr_document(payload)
    if dry_run:
        print("[lightrag] (dry-run) file_source=%s, %d байт" % (file_source, len(text.encode("utf-8"))))
        return
    with _LR_LOCK:
        try:
            _lr_wait_idle(cfg, "before update")
            existing = _lr_find_existing(cfg, file_source)
            if existing:
                _lr_request(cfg, "DELETE", "/documents/delete_document", {
                    "doc_ids": existing,
                    "delete_file": False,
                    "delete_llm_cache": True,
                }, timeout=120)
                print("[lightrag] переиндексация %s (удалил %d старых)" % (file_source, len(existing)))
                _lr_wait_idle(cfg, "delete", max_wait=300)
            body = _lr_request(cfg, "POST", "/documents/text",
                               {"text": text, "file_source": file_source}, timeout=120)
            print("[lightrag] залито %s -> track=%s" % (file_source, body.get("track_id", "?")))
        except Exception as e:
            sys.stderr.write("[lightrag] заливка не удалась (%s): %s\n" % (file_source, e))


def sink_lightrag(cfg, payload, src_path, dry_run):
    if not cfg["lightrag_url"]:
        return
    # Не блокируем цикл опроса — заливка (с ожиданием пайплайна) идёт в фоне.
    t = threading.Thread(target=_push_lightrag, args=(cfg, payload, src_path, dry_run), daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Обход файлов
# ---------------------------------------------------------------------------

def process_file(path, cfg, dry_run, seen):
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
    print("[watch] заметка готова: %s (%d задач)" % (
        payload.get("title") or "(без заголовка)", len(payload["action_items"])))
    sink_webhook(cfg, payload, dry_run)
    sink_lightrag(cfg, payload, path, dry_run)


def _sinks_banner(cfg, dry_run):
    parts = []
    parts.append("webhook=" + (cfg["webhook_url"] if cfg["webhook_url"] else "off"))
    parts.append("lightrag=" + (cfg["lightrag_url"] if cfg["lightrag_url"] else "off"))
    if dry_run:
        parts.append("(dry-run)")
    return ", ".join(parts)


def watch(cfg, dry_run):
    print("[watch] слежу за %s (опрос %ss) | %s" % (
        SESSIONS_DIR, POLL_SECONDS, _sinks_banner(cfg, dry_run)))
    if not dry_run and not cfg["webhook_url"] and not cfg["lightrag_url"]:
        print("[watch] ни один сток не настроен — только логирую готовность заметок")
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
                            process_file(p, cfg, dry_run, seen)
        except Exception as e:
            sys.stderr.write("[watch] scan error: %s\n" % e)
        first = False
        time.sleep(POLL_SECONDS)


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    cfg = load_config()

    if "--once" in args:
        path = args[args.index("--once") + 1]
        with open(path, encoding="utf-8") as f:
            payload = extract(f.read())
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if "--push" in args:
        path = args[args.index("--push") + 1]
        with open(path, encoding="utf-8") as f:
            payload = extract(f.read())
        payload["_source"] = path
        print("[push] %s | %s" % (payload.get("title") or "(без заголовка)", _sinks_banner(cfg, dry_run)))
        sink_webhook(cfg, payload, dry_run)
        # синхронно — иначе процесс завершится раньше фонового потока
        if cfg["lightrag_url"]:
            _push_lightrag(cfg, payload, path, dry_run)
        return

    watch(cfg, dry_run)


if __name__ == "__main__":
    main()
