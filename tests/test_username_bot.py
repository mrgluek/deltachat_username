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
os.environ["INVITE_BASE_URL"] = "https://i.gluek.info/#"

import database
from bot import (
    validate_username_format,
    validate_invite_link,
    rewrite_invite_link,
    extract_invite_link,
    clear_rate_limits,
    app,
)
from fastapi.testclient import TestClient


class TestUsernameBot(unittest.TestCase):
    def setUp(self):
        database.init_db()
        clear_rate_limits()
        self.client = TestClient(app)

    def tearDown(self):
        clear_rate_limits()
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

    def test_invite_link_validation_and_mirror_domain(self):
        valid_official_link = (
            "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
            "&v=3&i=W1VHKuRB8xripefA-rW-af3G&s=zfsEz5mBh2R5vQA0u-i6Mwev"
            "&a=gluek%40chatmail.uk&n=Gluek"
        )
        self.assertTrue(validate_invite_link(valid_official_link))

        valid_mirror_link = (
            "https://i.gluek.info/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
            "&v=3&i=W1VHKuRB8xripefA-rW-af3G&s=zfsEz5mBh2R5vQA0u-i6Mwev"
            "&a=gluek%40chatmail.uk&n=Gluek"
        )
        self.assertTrue(validate_invite_link(valid_mirror_link))

        # Channel / Broadcast invite link format test
        channel_link = (
            "https://i.delta.chat/#23753C03773D5FA52196017D60656FB4C682FA6C"
            "&v=3&x=4cfQHFUQjomc9UDGUWxzlmhH&j=RQ9JDugx5OwkVNPE-A55Rcu6"
            "&s=FEigHtgCiHEV172Ibqim9HDG&a=68h4f6okffwill7x%40dnd.wb.ru"
            "&n=%28m%E1%B5%89%29%E1%B5%88+%E2%89%A1+m+%28mod+_"
            "&b=%D0%A1%D0%B1%D0%BE%D1%80%D0%B8%D1%89%D0%B5+%D0%BD%D0%B0%D0%BA%D0%BB%D0%B5%D0%B5%D0%BA"
        )
        self.assertTrue(validate_invite_link(channel_link))

        invalid_link = "https://i.gluek.info/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        self.assertFalse(validate_invite_link(invalid_link))

    def test_rewrite_invite_link(self):
        official_link = "https://i.delta.chat/#12345?v=3&i=a&s=b&a=c&n=d"
        rewritten = rewrite_invite_link(official_link)
        self.assertTrue(rewritten.startswith("https://i.gluek.info/#"))

    def test_extract_invite_link(self):
        text = "Here is my link: https://i.gluek.info/#12345&v=3&i=a&s=b&a=c&n=d Thanks!"
        extracted = extract_invite_link(text)
        self.assertTrue(extracted.startswith("https://i.gluek.info/#"))

    def test_database_username_claims_and_single_chat_limit(self):
        link1 = "https://i.gluek.info/#12345?v=3&i=a&s=b&a=c&n=d"
        database.claim_username("first_name", link1, "chat_100")

        claim = database.get_username_claim("first_name")
        self.assertIsNotNone(claim)
        self.assertEqual(claim["username"], "first_name")
        self.assertEqual(claim["invite_link"], link1)
        self.assertEqual(claim["claimed_by_chat_id"], "chat_100")

        # Claim a new username for the same chat
        link2 = "https://i.gluek.info/#67890?v=3&i=a&s=b&a=c&n=d"
        database.claim_username("second_name", link2, "chat_100")

        # First username should be replaced and deleted
        self.assertIsNone(database.get_username_claim("first_name"))

        chat_claim = database.get_username_by_chat("chat_100")
        self.assertIsNotNone(chat_claim)
        self.assertEqual(chat_claim["username"], "second_name")

    def test_admin_multi_username_claim(self):
        user_link = "https://i.gluek.info/#111?v=3&i=a&s=b&a=c&n=d"
        channel_link = "https://i.gluek.info/#222?v=3&x=a&j=b&s=c&a=d&n=e"

        # Admin claims personal username
        database.claim_username("gluek", user_link, "admin_chat_id")

        # Admin claims secondary username for a channel using admin owner tag
        database.claim_username("stickers", channel_link, "admin_linked_stickers")

        # Both usernames must remain active simultaneously!
        claim1 = database.get_username_claim("gluek")
        claim2 = database.get_username_claim("stickers")

        self.assertIsNotNone(claim1)
        self.assertIsNotNone(claim2)
        self.assertEqual(claim1["username"], "gluek")
        self.assertEqual(claim2["username"], "stickers")

    def test_unlink_username(self):
        link = "https://i.gluek.info/#12345?v=3&i=a&s=b&a=c&n=d"
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

    def test_fastapi_endpoints_and_dynamic_redirect_rewrite(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Delta Chat Username Service", res.text)

        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

        res = self.client.get("/nonexistent")
        self.assertEqual(res.status_code, 404)

        # Even if stored as official i.delta.chat in DB, HTTP 307 redirect must dynamically rewrite to i.gluek.info
        old_official_link = "https://i.delta.chat/#ABC12345?v=3&i=1&s=2&a=test&n=test"
        database.claim_username("doesnm", old_official_link, "chat_100")

        res = self.client.get("/doesnm", follow_redirects=False)
        self.assertEqual(res.status_code, 307)
        self.assertEqual(res.headers["location"], "https://i.gluek.info/#ABC12345?v=3&i=1&s=2&a=test&n=test")

    def test_rate_limiting_get_username(self):
        clear_rate_limits()

        # First 10 requests within window should succeed (returning 404 or 307)
        for i in range(10):
            res = self.client.get(f"/test_uname_{i}")
            self.assertIn(res.status_code, (404, 307))

        # 11th request from the same IP should return 429 Too Many Requests
        res = self.client.get("/test_uname_11")
        self.assertEqual(res.status_code, 429)
        self.assertIn("Retry-After", res.headers)
        self.assertIn("Too many requests", res.text)


if __name__ == "__main__":
    unittest.main()
