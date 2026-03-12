import copy
import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager


OWNER_USER_ID = os.getenv("MAKE_CHAT_OWNER_USER_ID", "100000000")
BOT_USERNAME = os.getenv("MAKE_CHAT_BOT_USERNAME", "your_bot_username")
LEDGER_STALE_SECONDS = int(os.getenv("MAKE_CHAT_LEDGER_STALE_SECONDS", "300"))


def validate_title(raw_title: str) -> str:
    if raw_title is None:
        raise ValueError("title is required")

    title = raw_title.strip()
    if not title:
        raise ValueError("title is empty")
    if any(ord(ch) < 32 for ch in title):
        raise ValueError("title contains control characters")
    if "\x00" in title:
        raise ValueError("title contains NUL byte")
    if len(title) > 120:
        raise ValueError("title is too long")
    return title


def apply_group_policy(config: dict, chat_id: str) -> dict:
    updated = copy.deepcopy(config)
    telegram = updated.setdefault("channels", {}).setdefault("telegram", {})
    telegram["groupAllowFrom"] = [OWNER_USER_ID]
    groups = telegram.setdefault("groups", {})
    groups[chat_id] = {"enabled": True, "requireMention": False}
    return updated


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_ledger(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read().strip()
    return json.loads(content) if content else {}


def _write_json_atomic(path: str, payload: dict) -> None:
    ensure_parent_dir(path)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@contextmanager
def locked_file(path: str):
    ensure_parent_dir(path)
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        yield handle
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def claim_request(ledger_path: str, request_id: str, title: str) -> dict:
    now = int(time.time())
    with locked_file(ledger_path):
        ledger = load_ledger(ledger_path)
        entry = ledger.get(request_id)
        if entry:
            state = entry.get("state")
            updated_at = int(entry.get("updated_at", entry.get("created_at", now)))
            if state == "dm_reported":
                return {"status": "completed", "entry": entry}
            if now - updated_at <= LEDGER_STALE_SECONDS:
                return {"status": "duplicate", "entry": entry}
            entry["updated_at"] = now
            entry["recovered_at"] = now
            ledger[request_id] = entry
            _write_json_atomic(ledger_path, ledger)
            return {"status": "resume", "entry": entry}

        entry = {
            "request_id": request_id,
            "title": title,
            "state": "started",
            "created_at": now,
            "updated_at": now,
        }
        ledger[request_id] = entry
        _write_json_atomic(ledger_path, ledger)
        return {"status": "claimed", "entry": entry}


def record_state(ledger_path: str, request_id: str, state: str, **extra) -> dict:
    now = int(time.time())
    with locked_file(ledger_path):
        ledger = load_ledger(ledger_path)
        entry = ledger.setdefault(request_id, {"request_id": request_id, "created_at": now})
        entry["state"] = state
        entry["updated_at"] = now
        for key, value in extra.items():
            if value is not None:
                entry[key] = value
        ledger[request_id] = entry
        _write_json_atomic(ledger_path, ledger)
        return entry


def backup_and_write_config(config_path: str, backup_dir: str, config_lock_path: str, transform):
    os.makedirs(backup_dir, exist_ok=True)
    with locked_file(config_lock_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            current = json.load(handle)
        updated = transform(current)
        backup_path = os.path.join(
            backup_dir,
            f"openclaw.json.{time.strftime('%Y%m%d-%H%M%S')}.bak",
        )
        _write_json_atomic(backup_path, current)
        _write_json_atomic(config_path, updated)
        return updated, backup_path


def format_owner_success_message(result: dict) -> str:
    return (
        "Чат создан.\n"
        f"Название: {result['title']}\n"
        f"Chat ID: {result['chat_id']}\n"
        f"Бот: @{result['bot_username']} добавлен и подключён.\n"
        "В новом чате уже есть стартовое сообщение."
    )


def format_owner_failure_message(error: str, partial: dict | None = None) -> str:
    lines = ["Ошибка создания чата.", error]
    if partial:
        if partial.get("title"):
            lines.append(f"Название: {partial['title']}")
        if partial.get("chat_id"):
            lines.append(f"Chat ID: {partial['chat_id']}")
    return "\n".join(lines)
