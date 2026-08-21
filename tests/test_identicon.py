import unittest
import re
from datetime import datetime, timezone, timedelta
import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import identicon


class TestIdenticon(unittest.TestCase):
    def setUp(self):
        identicon.clear_png_cache()

    def test_emoji_palette_size(self):
        self.assertEqual(len(identicon.EMOJI_PALETTE), 256)
        # All emojis in palette must be non-empty strings
        for em in identicon.EMOJI_PALETTE:
            self.assertTrue(len(em) > 0)

    def test_format_fingerprint_groups(self):
        fp = "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        line1, line2 = identicon.format_fingerprint_groups(fp)
        self.assertEqual(line1, "DFF2 CAB1 FEB7 182F 997C")
        self.assertEqual(line2, "0A01 466A A64D E33D 8A39")

        # Test empty or short
        self.assertEqual(identicon.format_fingerprint_groups(""), ("", ""))
        l1, l2 = identicon.format_fingerprint_groups("ABCD1234EF567890")
        self.assertEqual(l1, "ABCD 1234")
        self.assertEqual(l2, "EF56 7890")

    def test_generate_symmetric_identicon(self):
        fp = "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        art = identicon.generate_symmetric_identicon(fp)
        self.assertIn("+---[ IDENTICON ]---+", art)
        self.assertIn("+-------------------+", art)

        lines = [l for l in art.split("\n") if l.startswith("|")]
        self.assertEqual(len(lines), 5)

        # Check horizontal symmetry for every line
        for line in lines:
            # line format is: "|   {c0}{c1}{c2}{c1}{c0}    |"
            content = line[4:14]  # 5 cells of 2 characters = 10 chars
            c0 = content[0:2]
            c1 = content[2:4]
            c2 = content[4:6]
            c3 = content[6:8]
            c4 = content[8:10]
            self.assertEqual(c0, c4, f"Column 0 should match column 4 in line: {line}")
            self.assertEqual(c1, c3, f"Column 1 should match column 3 in line: {line}")

    def test_identicon_determinism_and_uniqueness(self):
        fp1 = "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        fp2 = "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        fp3 = "1111222233334444555566667777888899990000"

        # Deterministic
        self.assertEqual(identicon.generate_symmetric_identicon(fp1), identicon.generate_symmetric_identicon(fp2))
        self.assertEqual(identicon.generate_emoji_hash(fp1), identicon.generate_emoji_hash(fp2))

        # Different keys give different hashes
        self.assertNotEqual(identicon.generate_emoji_hash(fp1), identicon.generate_emoji_hash(fp3))

    def test_generate_emoji_hash(self):
        fp = "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
        hash_5 = identicon.generate_emoji_hash(fp, count=5)
        emojis = hash_5.split()
        self.assertEqual(len(emojis), 5)
        for em in emojis:
            self.assertIn(em, identicon.EMOJI_PALETTE)

    def test_format_relative_time(self):
        now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

        # Just now (30 seconds ago)
        ts_now = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertIn("just now", identicon.format_relative_time(ts_now, now_dt=now))

        # 3 hours ago
        ts_hours = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertIn("3 hours ago", identicon.format_relative_time(ts_hours, now_dt=now))

        # 5 days ago
        ts_days = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertIn("5 days ago", identicon.format_relative_time(ts_days, now_dt=now))

        # Invalid timestamp fallback
        self.assertEqual(identicon.format_relative_time("invalid_date"), "invalid_date")
        self.assertEqual(identicon.format_relative_time(""), "Unknown date")

    def test_parse_invite_metadata(self):
        url = (
            "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39"
            "&v=3&i=token123&s=sig456&a=test%40example.com&n=Test+User"
        )
        meta = identicon.parse_invite_metadata(url, "2026-08-19T10:00:00Z")

        self.assertEqual(meta["fingerprint"], "DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39")
        self.assertEqual(meta["email"], "test@example.com")
        self.assertEqual(meta["display_name"], "Test User")
        self.assertEqual(meta["target_type"], "contact")
        self.assertEqual(meta["formatted_fp"][0], "DFF2 CAB1 FEB7 182F 997C")
        self.assertEqual(meta["formatted_fp"][1], "0A01 466A A64D E33D 8A39")
        self.assertTrue(len(meta["emoji_hash"].split()) == 5)
        self.assertIn("19 Aug 2026", meta["relative_time"])

    def test_parse_group_and_channel_metadata(self):
        group_url = "https://i.delta.chat/#AABBCCDDEEFF00112233&v=3&g=Chat+RU&s=sig&n=Username+Bot"
        meta_group = identicon.parse_invite_metadata(group_url)
        self.assertEqual(meta_group["target_type"], "group")
        self.assertEqual(meta_group["display_name"], "Chat RU")
        self.assertEqual(meta_group["inviter_name"], "Username Bot")

        channel_url = "https://i.delta.chat/#AABBCCDDEEFF00112233&v=3&b=News+Channel&s=sig&n=Author"
        meta_channel = identicon.parse_invite_metadata(channel_url)
        self.assertEqual(meta_channel["target_type"], "channel")
        self.assertEqual(meta_channel["display_name"], "News Channel")
        self.assertEqual(meta_channel["inviter_name"], "Author")

    def test_generate_svg_card(self):
        url = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=t&s=s&a=test%40example.com&n=Gluek"
        meta = identicon.parse_invite_metadata(url, "2026-08-19T10:00:00Z")
        svg = identicon.generate_svg_card("gluek", meta)

        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn("@gluek", svg)
        self.assertIn("test@example.com", svg)
        self.assertIn("DFF2 CAB1 FEB7 182F 997C", svg)

    def test_generate_og_png_bytes_and_cache(self):
        url = "https://i.delta.chat/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=t&s=s&a=test%40example.com&n=Gluek"
        meta = identicon.parse_invite_metadata(url, "2026-08-19T10:00:00Z")

        png1 = identicon.generate_og_png_bytes("gluek", meta)
        self.assertTrue(len(png1) > 0)
        # PNG signature check: \x89PNG\r\n\x1a\n
        self.assertTrue(png1.startswith(b"\x89PNG\r\n\x1a\n"))

        # Cached call
        png2 = identicon.generate_og_png_bytes("gluek", meta)
    def test_update_invite_link_contact_info(self):
        link = "https://i.deltachat.id/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&i=token123&s=sig456&a=old%40chatmail.uk&n=OldName"
        updated, changed = identicon.update_invite_link_contact_info(
            link, new_email="new@chatmail.uk", new_display_name="New Name"
        )
        self.assertTrue(changed)
        self.assertIn("a=new%40chatmail.uk", updated)
        self.assertIn("n=New+Name", updated)
        self.assertIn("i=token123", updated)
        self.assertIn("s=sig456", updated)

        # No change if same
        updated2, changed2 = identicon.update_invite_link_contact_info(
            updated, new_email="new@chatmail.uk", new_display_name="New Name"
        )
        self.assertFalse(changed2)
        self.assertEqual(updated, updated2)

        # Do not modify group links
        group_link = "https://i.deltachat.id/#DFF2CAB1FEB7182F997C0A01466AA64DE33D8A39&v=3&g=MyGroup&n=Admin"
        g_updated, g_changed = identicon.update_invite_link_contact_info(
            group_link, new_email="new@chatmail.uk", new_display_name="New Name"
        )
        self.assertFalse(g_changed)
        self.assertEqual(group_link, g_updated)


if __name__ == "__main__":
    unittest.main()
