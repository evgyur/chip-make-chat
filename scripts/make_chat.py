#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from make_chat_core import (
    BOT_USERNAME,
    OWNER_USER_ID,
    apply_group_policy,
    backup_and_write_config,
    claim_request,
    format_owner_failure_message,
    format_owner_success_message,
    record_state,
    validate_title,
)


HOME = Path.home()
API_BASE = os.getenv("MAKE_CHAT_API_BASE", "http://127.0.0.1:18080")
CONFIG_PATH = os.getenv("MAKE_CHAT_CONFIG_PATH", str(HOME / ".openclaw" / "openclaw.json"))
BACKUP_DIR = os.getenv(
    "MAKE_CHAT_BACKUP_DIR",
    str(HOME / ".cache" / "chip-make-chat" / "backups"),
)
CONFIG_LOCK_PATH = os.getenv(
    "MAKE_CHAT_CONFIG_LOCK_PATH",
    str(HOME / ".openclaw" / "locks" / "chip-make-chat.lock"),
)
LEDGER_PATH = os.getenv(
    "MAKE_CHAT_LEDGER_PATH",
    str(HOME / ".openclaw" / "state" / "chip-make-chat-ledger.json"),
)
BOT_TOKEN_FILE = os.getenv(
    "MAKE_CHAT_BOT_TOKEN_FILE",
    str(HOME / ".openclaw" / "secrets" / "telegram-bot-token"),
)
GATEWAY_STATUS_CMD = shlex.split(os.getenv("MAKE_CHAT_GATEWAY_STATUS_CMD", "openclaw gateway status"))
SUCCESS_MESSAGE = (
    "Чат создан и подключён. Бот активен. "
    f"Пиши с упоминанием @{BOT_USERNAME}."
)


class MakeChatError(Exception):
    pass


def print_json(payload, code=0):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(code)


def read_request(args):
    if args.request_file:
        with open(args.request_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    if args.request_json:
        return json.loads(args.request_json)
    if args.title is not None:
        title = validate_title(args.title)
        return {
            "from_user_id": args.from_user_id or OWNER_USER_ID,
            "chat_type": args.chat_type or "dm",
            "text": args.text or f"/make-chat {title}",
            "request_id": args.request_id or f"manual-{int(time.time())}",
        }
    raise MakeChatError("request payload is required")


def parse_title(text: str) -> str:
    stripped = (text or "").strip()
    prefixes = ("/make-chat", f"/make-chat@{BOT_USERNAME}")
    for prefix in prefixes:
        if stripped.startswith(prefix):
            return validate_title(stripped[len(prefix):])
    raise MakeChatError("command must start with /make-chat")


def api_request(method: str, path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def unwrap_response(response):
    if not response.get("success"):
        raise MakeChatError(response.get("error") or "telegram api request failed")
    data = response.get("data")
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)
    return data


def ensure_owner_identity():
    payload = unwrap_response(api_request("GET", "/me"))
    current_id = str(payload["id"])
    if current_id != OWNER_USER_ID:
        raise MakeChatError(f"telegram-chip-api identity mismatch: {current_id}")
    return payload


def create_supergroup(title: str):
    response = api_request(
        "POST",
        "/groups/supergroup",
        {
            "title": title,
            "about": title,
            "users": [],
            "topics_enabled": False,
        },
    )
    payload = unwrap_response(response)
    chat_id = str(payload["chat_id"])
    if not chat_id.startswith("-100"):
        raise MakeChatError(f"unexpected chat type: {chat_id}")
    return payload


def invite_bot_and_promote(chat_id: str):
    response = api_request(
        "POST",
        "/groups/invite-bot-admin",
        {
            "chat_id": int(chat_id),
            "bot_user_id": f"@{BOT_USERNAME}",
            "profile": "manager",
            "title": "Manager",
        },
    )
    return unwrap_response(response)


def probe_gateway_ready(timeout_seconds=45):
    deadline = time.time() + timeout_seconds
    last_output = ""
    while time.time() < deadline:
        completed = subprocess.run(
            GATEWAY_STATUS_CMD,
            capture_output=True,
            text=True,
            check=False,
        )
        last_output = completed.stdout + completed.stderr
        if completed.returncode == 0 and "RPC probe: ok" in last_output:
            return last_output
        time.sleep(2)
    raise MakeChatError(f"gateway readiness failed: {last_output.strip()}")


def send_bootstrap(chat_id: str):
    starter_text = (
        f"@{BOT_USERNAME} Напиши ровно это стартовое сообщение без изменений: "
        f"{SUCCESS_MESSAGE}"
    )
    response = api_request(
        "POST",
        "/messages/send",
        {
            "chat_id": int(chat_id),
            "message": starter_text,
        },
    )
    data = response.get("data", "")
    message_id = None
    if isinstance(data, str) and "Message ID:" in data:
        message_id = data.rsplit("Message ID:", 1)[-1].strip()
    return {"message_id": message_id, "text": starter_text}


def find_bot_reply(chat_id: str, timeout_seconds=45):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = api_request("GET", f"/chats/{chat_id}/messages?page=1&page_size=10")
        data = response.get("data", "")
        if SUCCESS_MESSAGE in data:
            return data
        time.sleep(3)
    raise MakeChatError("bot reply did not appear in the created chat")


def send_owner_dm(message: str):
    with open(BOT_TOKEN_FILE, "r", encoding="utf-8") as handle:
        token = handle.read().strip()
    if not token:
        raise MakeChatError("telegram bot token is empty")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": int(OWNER_USER_ID), "text": message}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not parsed.get("ok"):
        raise MakeChatError(f"bot sendMessage failed: {parsed}")
    return parsed


def orchestrate(request):
    from_user_id = str(request.get("from_user_id", ""))
    chat_type = str(request.get("chat_type", "")).lower()
    text = request.get("text", "")
    request_id = str(request.get("request_id") or request.get("update_id") or "")

    if not request_id:
        raise MakeChatError("request_id is required")
    if from_user_id != OWNER_USER_ID:
        raise MakeChatError("make-chat is not allowed for this user")

    context_note = None
    if chat_type not in {"", "dm", "direct", "private", "user"}:
        context_note = f"nonstandard_chat_type:{chat_type}"

    title = parse_title(text)
    claim = claim_request(LEDGER_PATH, request_id, title)
    if claim["status"] == "completed":
        return claim["entry"].get("result", claim["entry"])
    if claim["status"] == "duplicate":
        entry = claim["entry"]
        raise MakeChatError(
            f"request already in progress for {entry.get('title')} (state={entry.get('state')})"
        )

    entry = claim["entry"]
    ensure_owner_identity()

    chat_id = entry.get("chat_id")
    if not chat_id:
        created = create_supergroup(title)
        chat_id = str(created["chat_id"])
        record_state(
            LEDGER_PATH,
            request_id,
            "chat_created",
            chat_id=chat_id,
            result={"title": title, "chat_id": chat_id},
        )

    invite_bot_and_promote(chat_id)
    record_state(LEDGER_PATH, request_id, "bot_promoted", chat_id=chat_id)

    _, backup_path = backup_and_write_config(
        CONFIG_PATH,
        BACKUP_DIR,
        CONFIG_LOCK_PATH,
        lambda current: apply_group_policy(current, chat_id),
    )
    record_state(
        LEDGER_PATH,
        request_id,
        "config_applied",
        chat_id=chat_id,
        backup_path=backup_path,
    )

    probe_warning = None
    try:
        probe_gateway_ready()
    except MakeChatError as error:
        probe_warning = str(error)

    bootstrap = send_bootstrap(chat_id)
    bot_reply = find_bot_reply(chat_id)

    result = {
        "ok": True,
        "title": title,
        "chat_id": chat_id,
        "bot_username": BOT_USERNAME,
        "backup_path": backup_path,
        "bootstrap_message_id": bootstrap["message_id"],
        "bot_reply_seen": True,
        "bot_reply_excerpt": bot_reply.splitlines()[0],
    }
    if context_note:
        result["context_note"] = context_note
    if probe_warning:
        result["probe_warning"] = probe_warning
    send_owner_dm(format_owner_success_message(result))
    record_state(LEDGER_PATH, request_id, "dm_reported", chat_id=chat_id, result=result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-file")
    parser.add_argument("--request-json")
    parser.add_argument("--from-user-id")
    parser.add_argument("--chat-type")
    parser.add_argument("--text")
    parser.add_argument("--request-id")
    parser.add_argument("--title")
    args = parser.parse_args()

    request = None
    try:
        request = read_request(args)
        result = orchestrate(request)
        print_json(result, code=0)
    except MakeChatError as error:
        partial = None
        if request is not None and os.path.exists(LEDGER_PATH):
            try:
                request_id = str(request.get("request_id") or request.get("update_id") or "")
                if request_id:
                    with open(LEDGER_PATH, "r", encoding="utf-8") as handle:
                        ledger = json.load(handle)
                    partial = ledger.get(request_id)
            except Exception:
                partial = None
        if partial and str(request.get("from_user_id", "")) == OWNER_USER_ID:
            try:
                send_owner_dm(format_owner_failure_message(str(error), partial))
            except Exception:
                pass
        print_json({"ok": False, "error": str(error)}, code=1)
    except urllib.error.URLError as error:
        print_json({"ok": False, "error": f"telegram api unavailable: {error}"}, code=1)


if __name__ == "__main__":
    main()
