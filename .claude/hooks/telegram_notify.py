#!/usr/bin/env python3
"""Notification / Stop hook -> Telegram.

Привязка (см. settings.json):
- `Stop` — основной триггер, стреляет на каждое завершение хода Claude
  (в т.ч. после AskUserQuestion). AskUserQuestion как отдельный PreToolUse/
  Notification-триггер не работает в VSCode-extension окружении (проверено
  вручную 2026-08-09) — тул рендерится нативным UI и не идёт через hook
  pipeline вообще, поэтому зацепка через Stop, а не через сам тул.
- `Notification` — оставлен best-effort на случай терминального CLI
  (permission_prompt/idle_prompt и т.п.), в VSCode-extension практически
  не стреляет.

Токен/chat_id лежат в telegram.local.json рядом со скриптом (untracked,
см. .gitignore) — не хардкодим секрет в трекаемый settings.json/скрипт.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "telegram.local.json"


def main() -> int:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        token = config["bot_token"]
        chat_id = config["chat_id"]
    except Exception:
        # Нет конфига/токена — молча выходим, не роняем hook и не блокируем Claude.
        return 0

    try:
        # На Windows sys.stdin может декодироваться не как UTF-8 (локаль консоли) —
        # читаем сырые байты и декодируем явно, иначе кириллица ломается в суррогаты.
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        payload = {}

    event = payload.get("hook_event_name", "Notification")

    if event == "Stop":
        msg = "Claude закончил ответ, ждёт тебя"
    else:
        msg = payload.get("message") or payload.get("notification_type") or event

    session = payload.get("session_id", "")[:8]
    cwd = payload.get("cwd", "")

    text = f"\U0001f514 Claude Code\n{msg}"
    if cwd:
        text += f"\n{cwd}"
    if session:
        text += f"\nsession {session}"

    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=5
        )
    except Exception:
        pass  # уведомление best-effort, не должно валить hook

    return 0


if __name__ == "__main__":
    sys.exit(main())
