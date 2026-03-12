---
name: chip-make-chat
description: Owner-only Telegram command for creating a ready-to-use supergroup via `/make-chat` and wiring it into OpenClaw automatically.
metadata:
  clawdbot:
    emoji: "🏗️"
    command: /make-chat
    requires:
      bins: ["python3"]
---

# /make-chat

Create a thematic Telegram supergroup and finish the operational wiring in one run.

## Command

```text
/make-chat <chat title>
```

## When To Use

Use only when all of these are true:
- the incoming message starts with `/make-chat`
- the sender is the configured owner user id
- the command came from a direct chat with the bot

Do not run in groups.

## Preferred Execution

```bash
bash scripts/run_make_chat.sh "<chat title>"
```

Structured mode is also supported:

```bash
python3 scripts/make_chat.py --request-file <json-request-file>
```

The structured request JSON must contain:
- `from_user_id`
- `chat_type`
- `text`
- `request_id`

## Success Contract

On success, report:
1. created title
2. created `chat_id`
3. that the bot was added and promoted to `manager`
4. that the chat was allowlisted in OpenClaw
5. that a real bot reply appeared in the new chat

## Security Rules

- owner only
- direct-message only
- created groups stay `requireMention: false` for the owner-only allowlisted chats
- use lock + atomic config writes
- do not claim success until the real bot reply is visible in the new chat
