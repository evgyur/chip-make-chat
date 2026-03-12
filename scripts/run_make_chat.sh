#!/usr/bin/env bash
set -euo pipefail

TITLE="${*:-}"
if [[ -z "$TITLE" ]]; then
  printf '%s\n' '{"ok": false, "error": "title is required"}' >&2
  exit 1
fi

: "${MAKE_CHAT_OWNER_USER_ID:?set MAKE_CHAT_OWNER_USER_ID}"

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$BASE_DIR/make_chat.py" \
  --from-user-id "$MAKE_CHAT_OWNER_USER_ID" \
  --chat-type dm \
  --request-id "manual-$(date +%s)" \
  --title "$TITLE"
