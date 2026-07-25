import os
import sys
import tempfile
import time
import unittest

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use temporary database for testing
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = tmp_db.name

import database
from bot import validate_username_format, validate_invite_link, extract_invite_link, app
from fastapi.testclient import TestClient


class TestUsernameBot(unittest.TestCase):
    def setUp(self):
        database.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usernames")
        cursor.execute("DELETE FROM pending_usernames")
        cursor.execute("DELETE FROM config")
        conn.commit()
        conn.close()

    def test_username_validation(self):
        valid, msg = validate_username_format("ab")
        self.assertFalse(valid)
        self.assertIn("shorter than 3 characters", msg)

        valid, msg = validate_username_format("user@name")
        self.assertFalse(valid)
        self.assertIn("only contain letters", msg)

        valid, msg = validate_username_format("cat")
        self.assertTrue(valid)

        valid, msg = validate_username_format("gluek")
        self.assertTrue(valid)

        valid, msg = validate_username_format("my_group_123")
        self.assertTrue(valid)

    def test_invite_link_validation(self):
        valid_link = (
            "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
            "&v=3&i=W1VHKuRB8xripefA-rW-af3G&s=zfsEz5mBh2R5vQA0u-i6Mwev"
            "&a=gluek%40chatmail.uk&n=Gluek"
        )
        self.assertTrue(validate_invite_link(valid_link))

        invalid_link = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        self.assertFalse(validate_invite_link(invalid_link))

        wrong_domain = "https://example.com/#v=3&i=1&s=2&a=test&n=test"
        self.assertFalse(validate_invite_link(wrong_domain))

    def test_extract_invite_link(self):
        text = "Here is my link: https://i.delta.chat/#12345&v=3&i=a&s=b&a=c&n=d Thanks!"
        extracted = extract_invite_link(text)
        self.assertTrue(extracted.startswith("https://i.delta.chat/#"))

    def test_database_username_claims_and_single_chat_limit(self):
        link1 = "https://i.delta.chat/#12345?v=3&i=a&s=b&a=c&n=d"
        database.claim_username("first_name", link1, "chat_100")

        claim = database.get_username_claim("first_name")
        self.assertIsNotNone(claim)
        self.assertEqual(claim["username"], "first_name")
        self.assertEqual(claim["invite_link"], link1)
        self.assertEqual(claim["claimed_by_chat_id"], "chat_100")

        # Claim a new username for the same chat
        link2 = "https://i.delta.chat/#67890?v=3&i=a&s=b&a=c&n=d"
        database.claim_username("second_name", link2, "chat_100")

        # First username should be replaced and deleted
        self.assertIsNone(database.get_username_claim("first_name"))

        chat_claim = database.get_username_by_chat("chat_100")
        self.assertIsNotNone(chat_claim)
        self.assertEqual(chat_claim["username"], "second_name")

    def test_unlink_username(self):
        link = "https://i.delta.chat/#12345?v=3&i=a&s=b&a=c&n=d"
        database.claim_username("testname", link, "chat_300")

        unbound = database.unlink_chat_username("chat_300")
        self.assertEqual(unbound, "testname")
        self.assertIsNone(database.get_username_claim("testname"))
        self.assertIsNone(database.get_username_by_chat("chat_300"))

        # Test admin forced unlink by username
        database.claim_username("adminname", link, "chat_400")
        deleted = database.unlink_username("adminname")
        self.assertTrue(deleted)
        self.assertIsNone(database.get_username_claim("adminname"))

    def test_pending_username_expiration(self):
        database.set_pending_username("chat_200", "myusername")
        self.assertEqual(database.get_pending_username("chat_200"), "myusername")

        pending = database.get_pending_username("chat_200", ttl_seconds=-1)
        self.assertIsNone(pending)

    def test_fastapi_endpoints(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Delta Chat Username Service", res.text)

        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

        res = self.client.get("/nonexistent")
        self.assertEqual(res.status_code, 404)

        link = "https://i.delta.chat/#ABC12345?v=3&i=1&s=2&a=test&n=test"
        database.claim_username("gluek", link, "chat_100")

        res = self.client.get("/gluek", follow_redirects=False)
        self.assertEqual(res.status_code, 307)
        self.assertEqual(res.headers["location"], link)


if __name__ == "__main__":
    unittest.main()
