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
import identicon
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

        # Even if stored as official i.delta.chat in DB, the returned HTML must dynamically rewrite target_link
        old_official_link = "https://i.delta.chat/#ABC12345?v=3&i=1&s=2&a=test&n=test"
        database.claim_username("doesnm", old_official_link, "chat_100")

        res = self.client.get("/doesnm")
        self.assertEqual(res.status_code, 200)
        self.assertIn("https://i.gluek.info/#ABC12345?v=3&i=1&s=2&a=test&n=test", res.text)
        self.assertIn("window.location.replace", res.text)

    def test_rate_limiting_get_username(self):
        clear_rate_limits()

        # First 10 requests within window should succeed (returning 404 or 200)
        for i in range(10):
            res = self.client.get(f"/test_uname_{i}")
            self.assertIn(res.status_code, (404, 200))

    def test_crawler_opengraph_preview_and_meta_tags(self):
        link = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=1&s=2&a=gluek%40chatmail.uk&n=Gluek"
        database.claim_username("gluek", link, "chat_100")

        # 1. Normal Browser User-Agent should get 200 OK with OpenGraph tags and JS redirect
        res_browser = self.client.get(
            "/gluek",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        self.assertEqual(res_browser.status_code, 200)
        self.assertIn("og:title", res_browser.text)
        self.assertIn("og:image", res_browser.text)
        self.assertIn("window.location.replace", res_browser.text)

        # 2. TelegramBot Crawler User-Agent should get 200 OK with rich OpenGraph tags
        res_tg = self.client.get("/gluek", headers={"User-Agent": "TelegramBot (like TwitterBot)"})
        self.assertEqual(res_tg.status_code, 200)
        self.assertIn("og:title", res_tg.text)
        self.assertIn("og:image", res_tg.text)
        self.assertIn("gluek@chatmail.uk", res_tg.text)
        self.assertIn("DFF2 CAB1 FEB7 182F 997C", res_tg.text)

        # 3. Twitterbot Crawler User-Agent should get 200 OK
        res_twitter = self.client.get("/gluek", headers={"User-Agent": "Twitterbot/1.0"})
        self.assertEqual(res_twitter.status_code, 200)
        self.assertIn("summary_large_image", res_twitter.text)

        # 4. Explicit ?preview=1 in normal browser should get 200 OK
        res_preview = self.client.get("/gluek?preview=1")
        self.assertEqual(res_preview.status_code, 200)
        self.assertIn("Open in Delta Chat", res_preview.text)

    def test_dynamic_og_png_and_svg_endpoints(self):
        link = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=1&s=2&a=gluek%40chatmail.uk&n=Gluek"
        database.claim_username("gluek", link, "chat_100")

        # PNG endpoint
        res_png = self.client.get("/gluek/og.png")
        self.assertEqual(res_png.status_code, 200)
        self.assertEqual(res_png.headers["content-type"], "image/png")
        self.assertTrue(res_png.content.startswith(b"\x89PNG\r\n\x1a\n"))

        # SVG endpoints
        res_svg1 = self.client.get("/gluek/og.svg")
        self.assertEqual(res_svg1.status_code, 200)
        self.assertEqual(res_svg1.headers["content-type"], "image/svg+xml")
        self.assertIn("<svg", res_svg1.text)

        res_svg2 = self.client.get("/gluek/avatar.svg")
        self.assertEqual(res_svg2.status_code, 200)
        self.assertEqual(res_svg2.headers["content-type"], "image/svg+xml")

        # Non-existent user
        self.assertEqual(self.client.get("/ghost/og.png").status_code, 404)
        self.assertEqual(self.client.get("/ghost/og.svg").status_code, 404)

    def test_username_card_page(self):
        link = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=1&s=2&a=gluek%40chatmail.uk&n=Gluek"
        database.claim_username("gluek", link, "chat_100")

        res = self.client.get("/gluek/card")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Gluek", res.text)
        self.assertIn("@gluek", res.text)
        self.assertIn("gluek@chatmail.uk", res.text)
        self.assertIn("DFF2 CAB1 FEB7 182F 997C", res.text)
        self.assertIn("Start Chat in Delta Chat", res.text)

    def test_update_username_invite_metadata_and_sync(self):
        link = "https://i.deltachat.id/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=1&s=2&a=old%40chatmail.uk&n=Old"
        database.claim_username("synctest", link, "chat_sync")

        updated_link, changed = identicon.update_invite_link_contact_info(
            link, new_email="new@chatmail.uk", new_display_name="New Name"
        )
        self.assertTrue(changed)
        res = database.update_username_invite_metadata("synctest", updated_link)
        self.assertTrue(res)

        claim = database.get_username_claim("synctest")
        meta = identicon.parse_invite_metadata(claim["invite_link"])
        self.assertEqual(meta["email"], "new@chatmail.uk")
        self.assertEqual(meta["display_name"], "New Name")

    def test_username_command_sends_webp_card(self):
        from unittest.mock import MagicMock, patch
        import bot

        link = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=1&s=2&a=gluek%40chatmail.uk&n=Gluek"
        database.claim_username("botuser", link, "chat_200")

        mock_bot = MagicMock()
        mock_event = MagicMock()
        mock_event.msg.chat_id = 200
        mock_event.msg.from_id = 200
        mock_event.payload = "botuser"

        with patch.object(bot, "_dc_send_msg_with_stats") as mock_send:
            bot.username_command(mock_bot, 1, mock_event)
            self.assertTrue(mock_send.called)
            args, kwargs = mock_send.call_args
            msg_data = args[3]
            self.assertTrue(msg_data.text.startswith("https://i.delta.chat/#"))
            self.assertIsNotNone(msg_data.file)
            self.assertTrue(msg_data.file.endswith(".webp"))


if __name__ == "__main__":
    unittest.main()

