# chip-make-chat

Owner-only `/make-chat` skill for OpenClaw + `telegram-chip-api`.

It creates a Telegram supergroup, adds your bot, promotes it, allowlists the chat in `openclaw.json`, and waits for a real starter reply from the bot before reporting success.

## What It Assumes

- OpenClaw is already installed and running
- `telegram-chip-api` is running locally
- your bot token is stored in a readable file
- your owner account is authenticated in `telegram-chip-api`

## Files

- [SKILL.md](./SKILL.md): skill contract for OpenClaw
- [scripts/make_chat.py](./scripts/make_chat.py): orchestration helper
- [scripts/make_chat_core.py](./scripts/make_chat_core.py): config + ledger helpers
- [scripts/run_make_chat.sh](./scripts/run_make_chat.sh): simple wrapper
- [tests/test_make_chat_core.py](./tests/test_make_chat_core.py): unit tests
- [tests/test_make_chat_cli.py](./tests/test_make_chat_cli.py): CLI tests

## Environment

Copy `.env.example` values into your environment or service file.

Required:

- `MAKE_CHAT_OWNER_USER_ID`
- `MAKE_CHAT_BOT_USERNAME`

Usually also set:

- `MAKE_CHAT_API_BASE`
- `MAKE_CHAT_CONFIG_PATH`
- `MAKE_CHAT_BACKUP_DIR`
- `MAKE_CHAT_CONFIG_LOCK_PATH`
- `MAKE_CHAT_LEDGER_PATH`
- `MAKE_CHAT_BOT_TOKEN_FILE`
- `MAKE_CHAT_GATEWAY_STATUS_CMD`

## Example

```bash
export MAKE_CHAT_OWNER_USER_ID=123456789
export MAKE_CHAT_BOT_USERNAME=my_super_bot
export MAKE_CHAT_API_BASE=http://127.0.0.1:18080

bash scripts/run_make_chat.sh "New Thematic Chat"
```

## Tests

```bash
python3 -m unittest -v tests/test_make_chat_core.py tests/test_make_chat_cli.py
python3 -m py_compile scripts/make_chat_core.py scripts/make_chat.py
```
