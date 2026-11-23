"""1.18.1: the own fingerprint is read once per account, not on every message."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DB_PATH", tmp_db.name)

import commands
import database
import dc_fingerprint

SELF_FP = "D58B5E6C55482F94F9F5B84B6FB9FE3AD2658082"
PEER_FP = "0ECC037BAD768C41CA99B1F5F0B80E7D5DB13122"
ADMIN_FP = "DEC0E8D11FC4686F2C715C56F8C9AD699BC19AD8"
PEER_LINK = f"https://i.delta.chat/#{PEER_FP}&v=3&i=inv&s=auth&a=bob%40example.net&n=Bob"
INFO = (f"Messages are end-to-end encrypted.\nFingerprints:\n\nMe:\n{SELF_FP}\n\n"
        f"Bob:\n{PEER_FP}\n\nRelays:\nbob@example.net")
ADMIN_INFO = (f"Messages are end-to-end encrypted.\nFingerprints:\n\nMe:\n{SELF_FP}\n\n"
              f"Admin:\n{ADMIN_FP}\n\nRelays:\nadmin@example.net")


def make_bot(address, info):
    bot = MagicMock()
    bot.rpc.get_chat_securejoin_qr_code.return_value = f"https://i.delta.chat/#{SELF_FP}&v=3&i=a&s=b"
    bot.rpc.get_contact.return_value = SimpleNamespace(
        address=address, auth_name="X", name="", is_key_contact=True)
    bot.rpc.get_contact_encryption_info.return_value = info
    return bot


def message(chat_id=42, from_id=10):
    return SimpleNamespace(msg=SimpleNamespace(is_info=False, chat_id=chat_id, from_id=from_id))


class TestOwnFingerprintCache(unittest.TestCase):
    def setUp(self):
        database.init_db()
        dc_fingerprint.forget_self_fingerprint()
        conn = database.get_connection()
        for table in ("usernames", "config"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def test_helper_asks_the_core_once(self):
        rpc = make_bot("bob@example.net", INFO).rpc
        for _ in range(1000):
            self.assertEqual(dc_fingerprint.get_self_fingerprint(rpc, 1), SELF_FP)
        self.assertEqual(rpc.get_chat_securejoin_qr_code.call_count, 1)

    def test_failures_are_not_cached_and_accounts_are_separate(self):
        rpc = MagicMock()
        rpc.get_chat_securejoin_qr_code.side_effect = [Exception("down"), f"https://i.delta.chat/#{SELF_FP}&v=3"]
        self.assertIsNone(dc_fingerprint.get_self_fingerprint(rpc, 1))
        self.assertEqual(dc_fingerprint.get_self_fingerprint(rpc, 1), SELF_FP)
        rpc.get_chat_securejoin_qr_code.side_effect = None
        rpc.get_chat_securejoin_qr_code.return_value = f"https://i.delta.chat/#{PEER_FP}&v=3"
        self.assertEqual(dc_fingerprint.get_self_fingerprint(rpc, 2), PEER_FP)
        self.assertEqual(dc_fingerprint.get_self_fingerprint(rpc, 1), SELF_FP)
        dc_fingerprint.forget_self_fingerprint(rpc, 1)
        self.assertEqual(dc_fingerprint.get_self_fingerprint(rpc, 1), PEER_FP)

    def test_1000_messages_in_a_claimed_chat_cost_at_most_one_qr_call(self):
        database.claim_username("bob", PEER_LINK, "42")
        database.set_admin_email("admin@example.net")
        database.set_admin_fingerprint(ADMIN_FP)
        bot = make_bot("bob@example.net", INFO)
        for _ in range(1000):
            commands.on_new_message(bot, 1, message())
        self.assertLessEqual(bot.rpc.get_chat_securejoin_qr_code.call_count, 1)

    def test_1000_messages_in_a_plain_chat_cost_at_most_one_qr_call(self):
        database.set_admin_email("admin@example.net")
        database.set_admin_fingerprint(ADMIN_FP)
        bot = make_bot("bob@example.net", INFO)
        for _ in range(1000):
            commands.on_new_message(bot, 1, message())
        self.assertLessEqual(bot.rpc.get_chat_securejoin_qr_code.call_count, 1)

    def test_admin_check_skipped_when_nothing_to_upgrade(self):
        database.set_admin_email("admin@example.net")
        database.set_admin_fingerprint(ADMIN_FP)
        bot = make_bot("bob@example.net", INFO)
        commands.on_new_message(bot, 1, message())
        bot.rpc.get_contact.assert_not_called()
        bot.rpc.get_contact_encryption_info.assert_not_called()

    def test_admin_fingerprint_is_still_upgraded_once(self):
        database.set_admin_email("admin@example.net")
        bot = make_bot("admin@example.net", ADMIN_INFO)
        for _ in range(50):
            commands.on_new_message(bot, 1, message())
        self.assertEqual(database.get_admin_fingerprint(), ADMIN_FP)
        self.assertLessEqual(bot.rpc.get_chat_securejoin_qr_code.call_count, 1)
        self.assertEqual(bot.rpc.get_contact.call_count, 1)  # no more checks after the upgrade


if __name__ == "__main__":
    unittest.main()
