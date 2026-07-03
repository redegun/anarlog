# meeting-webhook (P0)

Следит за готовыми заметками anarlog и шлёт задачи/резюме встречи на webhook.
Работает без пересборки приложения: anarlog пишет заметку на диск
(`AppData/Roaming/com.hyprnote.dev/sessions/<id>/_summary.md`), watcher её парсит и POST'ит.

## Настройка
Укажи URL одним из способов:
- переменная окружения `WEBHOOK_URL=https://...`
- либо `config.json` рядом: `{ "webhook_url": "https://..." }`

Опционально: `WEBHOOK_AUTH="Bearer <token>"` → уйдёт в заголовок Authorization.

## Запуск
    py watch.py                 # следить (фон)
    py watch.py --dry-run       # следить, печатать JSON вместо отправки
    py watch.py --once <file>   # разобрать один _summary.md (дебаг)

## Payload
    {
      "session_id": "...", "note_id": "...",
      "title": "Заголовок встречи",
      "action_items": ["...", "..."],   // из секции «Задачи»/«Action Items»
      "summary_md": "полный markdown резюме"
    }

Дальше этот URL можно завести на Telegram-бота, n8n, CRM — что угодно.
