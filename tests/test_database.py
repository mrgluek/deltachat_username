import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

TEST_DB = "test_username_db.db"


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.orig_db = database.DB_PATH
        database.DB_PATH = TEST_DB
        database.init_db()
        with database._transport_stats_lock:
            database._transport_stats_buffer.clear()

    def tearDown(self):
        with database._transport_stats_lock:
            database._transport_stats_buffer.clear()
        database.DB_PATH = self.orig_db
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except OSError:
                pass
        for suffix in ["-wal", "-shm"]:
            fpath = TEST_DB + suffix
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass

    def test_config_roundtrip(self):
        self.assertIsNone(database.get_config("nonexistent_key"))
        database.set_config("key1", "val1")
        self.assertEqual(database.get_config("key1"), "val1")
        database.set_config("key1", "val2")
        self.assertEqual(database.get_config("key1"), "val2")

    def test_admin_email_normalization(self):
        self.assertIsNone(database.get_admin_email())
        database.set_admin_email("  ADMIN@Example.COM  ")
        self.assertEqual(database.get_admin_email(), "admin@example.com")

    def test_admin_fingerprint_handling(self):
        self.assertIsNone(database.get_admin_fingerprint())
        database.set_admin_fingerprint("aa:bb:cc:dd:11:22:33:44:55:66:77:88:99:00:11:22")
        self.assertEqual(database.get_admin_fingerprint(), "AABBCCDD112233445566778899001122")

        # Invalid fingerprint rejected
        database.set_admin_fingerprint("not_a_valid_fp")
        self.assertIsNone(database.get_admin_fingerprint())

        # Clear fingerprint
        database.set_admin_fingerprint("")
        self.assertIsNone(database.get_admin_fingerprint())

    def test_is_authorized_sender(self):
        # No admin configured
        self.assertFalse(database.is_authorized_sender("user@example.com"))

        # Email only configured
        database.set_admin_email("admin@example.com")
        self.assertTrue(database.is_authorized_sender("admin@example.com"))
        self.assertTrue(database.is_authorized_sender(" ADMIN@example.COM "))
        self.assertFalse(database.is_authorized_sender("intruder@example.com"))

        # Fingerprint configured as well
        fp = "AABBCCDD112233445566778899001122"
        database.set_admin_fingerprint(fp)
        self.assertTrue(database.is_authorized_sender("admin@example.com", fp))
        self.assertTrue(database.is_authorized_sender("admin@example.com", "aa:bb:cc:dd:11:22:33:44:55:66:77:88:99:00:11:22"))
        self.assertFalse(database.is_authorized_sender("admin@example.com", "WRONGFP112233445566778899001122"))
        # Email alone fails when fingerprint is required
        self.assertFalse(database.is_authorized_sender("admin@example.com"))

    def test_transport_stats_buffering_and_flush(self):
        addr1 = "relay1@example.com"
        addr2 = "relay2@example.com"

        database.increment_transport_sent(addr1)
        database.increment_transport_sent(addr1)
        database.increment_transport_received(addr1)
        database.increment_transport_received(addr2)

        stats = database.get_all_transport_stats()
        stats_map = {s["addr"]: s for s in stats}

        self.assertIn(addr1, stats_map)
        self.assertIn(addr2, stats_map)
        self.assertEqual(stats_map[addr1]["msgs_sent"], 2)
        self.assertEqual(stats_map[addr1]["msgs_received"], 1)
        self.assertIsNotNone(stats_map[addr1]["last_sent_at"])
        self.assertIsNotNone(stats_map[addr1]["last_received_at"])

        self.assertEqual(stats_map[addr2]["msgs_sent"], 0)
        self.assertEqual(stats_map[addr2]["msgs_received"], 1)

    def test_cleanup_old_records(self):
        res = database.cleanup_old_records()
        self.assertEqual(res.get("status"), "ok")


    def _set_times(self, username, linked_at, updated_at):
        conn = database.get_connection()
        conn.execute(
            "UPDATE usernames SET linked_at = ?, updated_at = ? WHERE username = ?",
            (linked_at, updated_at, username),
        )
        conn.commit()
        conn.close()

    def test_linked_at_survives_link_updates(self):
        database.claim_username("alice", "https://i.delta.chat/#A&a=old", "10")
        self._set_times("alice", "2026-07-26T10:00:00Z", "2026-07-26T10:00:00Z")

        # Contact sync rewrites the link: only updated_at moves
        database.update_username_invite_metadata("alice", "https://i.delta.chat/#A&a=new")
        claim = database.get_username_claim("alice")
        self.assertEqual(claim["linked_at"], "2026-07-26T10:00:00Z")
        self.assertNotEqual(claim["updated_at"], "2026-07-26T10:00:00Z")

        # The same chat re-linking the same name keeps the claim date
        database.claim_username("alice", "https://i.delta.chat/#A&a=newer", "10")
        self.assertEqual(database.get_username_claim("alice")["linked_at"], "2026-07-26T10:00:00Z")

        # A new name, or the name taken over by another chat, starts a new claim
        database.claim_username("alice2", "https://i.delta.chat/#A", "10")
        self.assertNotEqual(database.get_username_claim("alice2")["linked_at"], "2026-07-26T10:00:00Z")
        database.claim_username("bob", "https://i.delta.chat/#B", "20")
        self._set_times("bob", "2026-07-26T10:00:00Z", "2026-07-26T10:00:00Z")
        database.claim_username("bob", "https://i.delta.chat/#C", "30")
        self.assertNotEqual(database.get_username_claim("bob")["linked_at"], "2026-07-26T10:00:00Z")

    def test_linked_at_migration_from_updated_at(self):
        # Pre-1.18 table without linked_at
        conn = database.get_connection()
        conn.execute("DROP TABLE usernames")
        conn.execute(
            "CREATE TABLE usernames (username TEXT PRIMARY KEY, invite_link TEXT NOT NULL, "
            "claimed_by_chat_id TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO usernames VALUES ('old', 'https://i.delta.chat/#A', '1', '2026-08-01T00:00:00Z')")
        conn.commit()
        conn.close()

        database.init_db()
        database.init_db()  # idempotent
        self.assertEqual(database.get_username_claim("old")["linked_at"], "2026-08-01T00:00:00Z")
        self.assertEqual(database.get_all_usernames()["old"]["linked_at"], "2026-08-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
