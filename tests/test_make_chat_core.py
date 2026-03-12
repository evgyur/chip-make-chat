import os
import sys
import tempfile
import unittest


SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPT_DIR))

from make_chat_core import (  # type: ignore
    BOT_USERNAME,
    OWNER_USER_ID,
    apply_group_policy,
    claim_request,
    format_owner_failure_message,
    format_owner_success_message,
    load_ledger,
    record_state,
    validate_title,
)


def base_config():
    return {
        "channels": {
            "telegram": {
                "groupAllowFrom": ["1", OWNER_USER_ID, "2"],
                "groups": {"*": {"enabled": False, "requireMention": True}},
            }
        }
    }


class TitleValidationTests(unittest.TestCase):
    def test_rejects_empty_title_after_trim(self):
        with self.assertRaises(ValueError):
            validate_title("   ")

    def test_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            validate_title("bad\nname")

    def test_keeps_regular_title(self):
        self.assertEqual(validate_title("  Den's Nedviga  "), "Den's Nedviga")


class ConfigMutationTests(unittest.TestCase):
    def test_sets_exact_owner_only_group_policy(self):
        updated = apply_group_policy(base_config(), "-100123")
        telegram = updated["channels"]["telegram"]
        self.assertEqual(telegram["groupAllowFrom"], [OWNER_USER_ID])
        self.assertEqual(
            telegram["groups"]["-100123"],
            {"enabled": True, "requireMention": False},
        )


class LedgerTests(unittest.TestCase):
    def test_claim_request_prevents_duplicate_create(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = os.path.join(tmpdir, "ledger.json")
            first = claim_request(ledger_path, "update-1", "Den's Nedviga")
            second = claim_request(ledger_path, "update-1", "Den's Nedviga")
            self.assertEqual(first["status"], "claimed")
            self.assertEqual(second["status"], "duplicate")
            self.assertEqual(second["entry"]["state"], "started")

    def test_record_state_persists_chat_id_for_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = os.path.join(tmpdir, "ledger.json")
            claim_request(ledger_path, "update-2", "Den's Nedviga")
            record_state(
                ledger_path,
                "update-2",
                "chat_created",
                chat_id="-100456",
                result={"chat_id": "-100456"},
            )
            ledger = load_ledger(ledger_path)
            self.assertEqual(ledger["update-2"]["chat_id"], "-100456")


class OwnerMessageFormattingTests(unittest.TestCase):
    def test_formats_success_message_with_chat_id(self):
        text = format_owner_success_message(
            {
                "title": "Den's Nedviga",
                "chat_id": "-100123",
                "bot_username": BOT_USERNAME,
            }
        )
        self.assertIn("Den's Nedviga", text)
        self.assertIn("-100123", text)
        self.assertIn(f"@{BOT_USERNAME}", text)

    def test_formats_failure_message_with_partial_chat_id(self):
        text = format_owner_failure_message(
            "gateway readiness failed",
            {"title": "Den's Nedviga", "chat_id": "-100123"},
        )
        self.assertIn("gateway readiness failed", text)
        self.assertIn("-100123", text)


if __name__ == "__main__":
    unittest.main()
