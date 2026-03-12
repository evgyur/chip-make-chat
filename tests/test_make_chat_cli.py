import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

import make_chat  # type: ignore
from make_chat_core import BOT_USERNAME, OWNER_USER_ID  # type: ignore


SCRIPT_PATH = os.path.join(SCRIPT_DIR, "make_chat.py")


class CliGuardTests(unittest.TestCase):
    def run_script(self, payload):
        with tempfile.NamedTemporaryFile("w", delete=False) as request_file:
            json.dump(payload, request_file)
            request_file.flush()
            request_path = request_file.name
        try:
            completed = subprocess.run(
                [sys.executable, SCRIPT_PATH, "--request-file", request_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(request_path)
        return completed

    def test_rejects_non_owner_dm(self):
        completed = self.run_script(
            {
                "from_user_id": "999",
                "chat_type": "dm",
                "text": "/make-chat Test",
                "request_id": "r1",
            }
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not allowed", completed.stdout + completed.stderr)

    def test_rejects_non_owner_group_invocation(self):
        completed = self.run_script(
            {
                "from_user_id": "999",
                "chat_type": "group",
                "text": "/make-chat Test",
                "request_id": "r2",
            }
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not allowed", completed.stdout + completed.stderr)

    def test_accepts_manual_shortcut_args(self):
        completed = subprocess.run(
            [
                sys.executable,
                SCRIPT_PATH,
                "--from-user-id",
                OWNER_USER_ID,
                "--chat-type",
                "dm",
                "--request-id",
                "manual-r1",
                "--title",
                "Manual Test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotIn("request payload is required", completed.stdout + completed.stderr)

    def test_send_bootstrap_requires_mention(self):
        with mock.patch.object(make_chat, "api_request", return_value={"data": "Message ID: 7"}):
            result = make_chat.send_bootstrap("-100123")
        self.assertEqual(result["message_id"], "7")
        self.assertIn(f"@{BOT_USERNAME}", result["text"])
        self.assertIn(f"Пиши с упоминанием @{BOT_USERNAME}.", result["text"])


if __name__ == "__main__":
    unittest.main()
