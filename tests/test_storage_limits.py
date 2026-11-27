"""1.18.2: the bot profile sets download_limit and 24 h local auto-delete."""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DB_PATH", tmp_db.name)

import dc_helpers


class StorageLimitsTest(unittest.TestCase):
    def test_both_limits_are_set(self):
        bot = MagicMock()
        dc_helpers.configure_bot_profile(bot, 7)
        calls = [c.args for c in bot.rpc.set_config.call_args_list]
        self.assertIn((7, "download_limit", "65536"), calls)
        self.assertIn((7, "delete_device_after", "86400"), calls)

    def test_delete_failure_does_not_block_and_is_logged(self):
        bot = MagicMock()

        def fail(accid, key, value):
            if key == "delete_device_after":
                raise RuntimeError("boom")

        bot.rpc.set_config.side_effect = fail
        dc_helpers.configure_bot_profile(bot, 7)
        self.assertTrue(any("delete_device_after" in c.args[0]
                            for c in bot.logger.warning.call_args_list))


if __name__ == "__main__":
    unittest.main()
