# meeting-webhook (P0 + P1)

Следит за готовыми заметками anarlog и рассылает их по стокам. Работает без пересборки
приложения: anarlog пишет заметку на диск
(`AppData/Roaming/com.hyprnote.dev/sessions/<id>/_summary.md`), watcher её парсит и раздаёт.

Два независимых стока (можно включить любой, оба, или ни одного):

- **P0 · webhook** — задачи + резюме встречи POST'ятся JSON'ом на настраиваемый URL
  (Telegram-бот / CRM / n8n).
- **P1 · lightrag** — полный markdown резюме заливается в LightRAG на VPS для чата
  по всей истории встреч (cross-meeting RAG). Одна встреча = один документ,
  при повторной генерации переиндексируется (старый удаляется, новый заливается).

## Настройка

Через переменные окружения **или** `config.json` рядом (env приоритетнее):

| Что | env | config.json | Назначение |
|---|---|---|---|
| P0 URL | `WEBHOOK_URL` | `webhook_url` | включает webhook-сток |
| P0 auth | `WEBHOOK_AUTH` | `webhook_auth` | заголовок `Authorization` |
| P1 URL | `LIGHTRAG_URL` | `lightrag_url` | включает LightRAG-сток |
| P1 key | `LIGHTRAG_API_KEY` | `lightrag_api_key` | `X-API-Key` (дефолт — ключ neprosto) |

Пример `config.json`:

    {
      "webhook_url": "https://your-endpoint/hook",
      "webhook_auth": "Bearer XXX",
      "lightrag_url": "http://127.0.0.1:9621",
      "lightrag_api_key": "lightrag-neprosto-api-key-2026"
    }

**P1 требует доступа к LightRAG.** LightRAG живёт на VPS (`clou-server`, порт 9621).
С этой машины он виден на `http://127.0.0.1:9621`, пока поднят ssh-тоннель
(`tools/ssh_tunnel/tunnel.bat` в рабочем пространстве). Пусто = сток выключен.

## Запуск

    py watch.py                 # следить (фон), раздавать по включённым стокам
    py watch.py --dry-run       # следить, печатать вместо отправки
    py watch.py --once <file>   # разобрать один _summary.md → payload (дебаг парсера)
    py watch.py --push <file>   # разово прогнать один _summary.md по стокам (тест стоков)

## Payload (P0 webhook)

    {
      "session_id": "...", "note_id": "...",
      "title": "Заголовок встречи",
      "action_items": ["...", "..."],   // из секции «Задачи»/«Action Items»
      "summary_md": "полный markdown резюме"
    }

Дальше этот URL можно завести на Telegram-бота, n8n, CRM — что угодно.

## Что уходит в LightRAG (P1)

Заголовок-контекст (`Встреча (заметки Anarlog): <title>` + session) и полное резюме встречи.
`file_source` = `anarlog-meeting/<session_id>.md` — стабильный идентификатор, по которому
док находится и переиндексируется. После заливки чат по истории:

    ssh clou-server "cd /root/.openclaw/workspace && bash scripts/lightrag-query.sh 'что обсуждали на встречах про X'"
