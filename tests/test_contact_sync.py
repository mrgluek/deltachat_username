import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DB_PATH", tmp_db.name)

import contact_sync
import database
import identicon

BOB_FP = "0ECC037BAD768C41CA99B1F5F0B80E7D5DB13122"

# Real output of get_contact_encryption_info (core 2.65) for a key contact
ENC_INFO = (
    "Messages are end-to-end encrypted.\nFingerprints:\n\n"
    "Me (alice@example.org):\nCB01 52E1 D9F6 E11E FDE5\n4D1D C04B 874C 77FA 1390\n\n"
    "Bob (bob@example.net):\n0ECC 037B AD76 8C41 CA99\nB1F5 F0B8 0E7D 5DB1 3122\n\n"
    "Relays:\nbob@new.example\nbob@example.net\nbob@third.example"
)

BOB_LINK = f"https://i.delta.chat/#{BOB_FP}&v=3&i=inv&s=auth&a=bob%40example.net&n=Bob"


def _params(link):
    return parse_qs(link.split("/#", 1)[1].split("&", 1)[1])


class TestParsing(unittest.TestCase):
    def test_contact_fingerprint_picked_by_address(self):
        self.assertEqual(contact_sync.parse_contact_fingerprint(ENC_INFO, "bob@example.net"), BOB_FP)
        # The bot's own block is never taken for the contact's
        self.assertEqual(
            contact_sync.parse_contact_fingerprint(ENC_INFO, "alice@example.org"),
            "CB0152E1D9F6E11EFDE54D1DC04B874C77FA1390",
        )
        self.assertEqual(contact_sync.parse_contact_fingerprint(ENC_INFO, "carol@example.com"), "")
        self.assertEqual(contact_sync.parse_contact_fingerprint("No encryption.", "bob@example.net"), "")

    def test_relays(self):
        self.assertEqual(
            contact_sync.parse_relays(ENC_INFO),
            ["bob@new.example", "bob@example.net", "bob@third.example"],
        )
        self.assertEqual(contact_sync.parse_relays(ENC_INFO.split("\n\nRelays:")[0]), [])
        self.assertEqual(contact_sync.parse_relays(""), [])


class TestLinkUpdate(unittest.TestCase):
    def test_keeps_current_address_and_lists_other_relays(self):
        link, changed = identicon.update_invite_link_contact_info(
            BOB_LINK, new_email="bob@example.net", new_relays=["bob@new.example", "bob@example.net", "bob@third.example"]
        )
        self.assertTrue(changed)
        self.assertIn("&a=bob%40example.net&r=bob%40new.example,bob%40third.example&", link)
        self.assertEqual(_params(link)["i"], ["inv"])

    def test_address_moves_to_a_listed_relay(self):
        link, changed = identicon.update_invite_link_contact_info(
            BOB_LINK, new_email="bob@gone.example", new_relays=["bob@new.example", "bob@third.example"]
        )
        self.assertTrue(changed)
        params = _params(link)
        self.assertEqual(params["a"], ["bob@new.example"])
        self.assertEqual(params["r"], ["bob@third.example"])

    def test_single_relay_drops_r(self):
        with_r = BOB_LINK + "&r=bob%40old.example"
        link, changed = identicon.update_invite_link_contact_info(
            with_r, new_email="bob@example.net", new_relays=["bob@example.net"]
        )
        self.assertTrue(changed)
        self.assertNotIn("r=", link)

    def test_unchanged(self):
        link = BOB_LINK.replace("&n=Bob", "&r=bob%40new.example&n=Bob")
        _, changed = identicon.update_invite_link_contact_info(
            link, new_email="bob@example.net", new_display_name="Bob",
            new_relays=["bob@example.net", "bob@new.example"],
        )
        self.assertFalse(changed)

    def test_name_change_keeps_r_unbroken(self):
        # Existing r= must stay a raw comma list: the core splits it before decoding
        link = BOB_LINK + "&r=bob%40x.example,bob%40y.example"
        updated, changed = identicon.update_invite_link_contact_info(link, new_display_name="Robert")
        self.assertTrue(changed)
        self.assertIn("r=bob%40x.example,bob%40y.example", updated)
        self.assertNotIn("%2C", updated)


class TestSyncClaim(unittest.TestCase):
    def setUp(self):
        database.init_db()
        self.bot = MagicMock()
        self.bot.rpc.get_contact.return_value = SimpleNamespace(
            address="bob@example.net", auth_name="Bobby", name="", is_key_contact=True
        )
        self.bot.rpc.get_contact_encryption_info.return_value = ENC_INFO

    def tearDown(self):
        conn = database.get_connection()
        conn.execute("DELETE FROM usernames")
        conn.commit()
        conn.close()

    def test_updates_own_link(self):
        database.claim_username("bob", BOB_LINK, "42")
        self.assertTrue(contact_sync.sync_claim(self.bot, 1, database.get_username_claim("bob"), 10))
        params = _params(database.get_username_claim("bob")["invite_link"])
        self.assertEqual(params["a"], ["bob@example.net"])
        self.assertEqual(params["r"], ["bob@new.example,bob@third.example"])
        self.assertEqual(params["n"], ["Bobby"])

    def test_foreign_key_is_not_touched(self):
        other = BOB_LINK.replace(BOB_FP, "AAAA" * 10)
        database.claim_username("other", other, "42")
        self.assertFalse(contact_sync.sync_claim(self.bot, 1, database.get_username_claim("other"), 10))
        self.assertEqual(database.get_username_claim("other")["invite_link"], other)

    def test_group_link_is_not_touched(self):
        group = BOB_LINK + "&x=abcdefghijkl&g=Team"
        database.claim_username("team", group, "42")
        self.assertFalse(contact_sync.sync_claim(self.bot, 1, database.get_username_claim("team"), 10))
        self.bot.rpc.get_contact.assert_not_called()

    def test_address_contact_is_skipped(self):
        self.bot.rpc.get_contact.return_value = SimpleNamespace(address="bob@example.net", is_key_contact=False)
        database.claim_username("bob", BOB_LINK, "42")
        self.assertFalse(contact_sync.sync_claim(self.bot, 1, database.get_username_claim("bob"), 10))

    @patch("contact_sync._is_private_chat", return_value=True)
    def test_sync_all_claims(self, _private):
        database.claim_username("bob", BOB_LINK, "42")
        database.claim_username("chan", BOB_LINK + "&x=abcdefghijkl&j=1&b=News", "admin_chan")
        self.bot.rpc.get_full_chat_by_id.return_value = SimpleNamespace(contact_ids=[1, 10])
        self.assertEqual(contact_sync.sync_all_claims(self.bot, 1), 1)
        self.bot.rpc.get_full_chat_by_id.assert_called_once_with(1, 42)


if __name__ == "__main__":
    unittest.main()
