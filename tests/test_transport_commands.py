import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import deltachat2
except ImportError:
    mock_deltachat2 = MagicMock()
    class MsgData:
        def __init__(self, text="", file="", override_sender_name=None):
            self.text = text
            self.file = file
            self.override_sender_name = override_sender_name
    mock_deltachat2.MsgData = MsgData
    sys.modules['deltachat2'] = mock_deltachat2

try:
    import deltabot_cli
except ImportError:
    class MockBotCli:
        def __init__(self, *args, **kwargs):
            pass
        def on(self, *args, **kwargs):
            return lambda func: func
        def on_init(self, func):
            return func
        def on_start(self, func):
            return func
        def start(self):
            pass
    mock_deltabot_cli = MagicMock()
    mock_deltabot_cli.BotCli = MockBotCli
    sys.modules['deltabot_cli'] = mock_deltabot_cli

import database
import commands
import dc_helpers

TEST_DB_PATH = "test_username_transport_cmds.db"


class TestTransportCommands(unittest.TestCase):
    def setUp(self):
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = TEST_DB_PATH
        with database._transport_stats_lock:
            database._transport_stats_buffer.clear()
        database.init_db()

        self.mock_bot = MagicMock()
        self.mock_event = MagicMock()
        self.mock_msg = MagicMock()
        self.mock_msg.from_id = 100
        self.mock_msg.chat_id = 10
        self.mock_msg.file = None
        self.mock_event.msg = self.mock_msg
        self.mock_event.payload = ""
        self.accid = 1

        mock_contact = MagicMock()
        mock_contact.address = "admin@example.com"
        self.mock_bot.rpc.get_contact.return_value = mock_contact

    def tearDown(self):
        database.DB_PATH = self.orig_db_path
        with database._transport_stats_lock:
            database._transport_stats_buffer.clear()
        for f in (TEST_DB_PATH, f"{TEST_DB_PATH}-wal", f"{TEST_DB_PATH}-shm"):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    # ── /initadmin ─────────────────────────────────────────────────────────

    @patch("commands._is_private_chat")
    def test_initadmin_rejected_in_group_chat(self, mock_is_private):
        mock_is_private.return_value = False
        commands.initadmin_command(self.mock_bot, self.accid, self.mock_event)
        self.mock_bot.rpc.send_msg.assert_called_once()
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("only be used in a private 1:1 chat", msg_text)

    @patch("commands._get_contact_fingerprint")
    @patch("commands._is_private_chat")
    def test_initadmin_success(self, mock_is_private, mock_get_fp):
        mock_is_private.return_value = True
        mock_get_fp.return_value = "AABBCCDDAABBCCDDAABBCCDDAABBCCDD"
        commands.initadmin_command(self.mock_bot, self.accid, self.mock_event)
        self.assertEqual(database.get_admin_email(), "admin@example.com")
        self.assertEqual(database.get_admin_fingerprint(), "AABBCCDDAABBCCDDAABBCCDDAABBCCDD")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("You are now confirmed as admin", msg_text)

    @patch("commands._is_private_chat")
    def test_initadmin_already_set(self, mock_is_private):
        mock_is_private.return_value = True
        database.set_admin_email("admin@example.com")
        database.set_admin_fingerprint("AABBCCDDAABBCCDDAABBCCDDAABBCCDD")
        commands.initadmin_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Admin is already set", msg_text)

    # ── /addtransport ───────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_addtransport_non_admin_rejected(self, mock_admin):
        mock_admin.return_value = False
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("only for the administrator", msg_text)

    @patch("commands._is_dc_admin")
    @patch("commands._is_private_chat")
    def test_addtransport_rejected_in_group(self, mock_is_private, mock_admin):
        mock_admin.return_value = True
        mock_is_private.return_value = False
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("only be used in a private 1:1 chat", msg_text)

    @patch("commands._is_dc_admin")
    @patch("commands._is_private_chat")
    def test_addtransport_empty_payload(self, mock_is_private, mock_admin):
        mock_admin.return_value = True
        mock_is_private.return_value = True
        self.mock_event.payload = ""
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Usage:", msg_text)

    @patch("commands._is_dc_admin")
    @patch("commands._is_private_chat")
    def test_addtransport_success_qr(self, mock_is_private, mock_admin):
        mock_admin.return_value = True
        mock_is_private.return_value = True
        self.mock_event.payload = "DCACCOUNT:chatmail.example.org"
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        self.mock_bot.rpc.add_transport_from_qr.assert_called_once_with(self.accid, "DCACCOUNT:chatmail.example.org")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Backup transport added via chatmail URI", msg_text)

    @patch("commands._is_dc_admin")
    @patch("commands._is_private_chat")
    def test_addtransport_success_credentials(self, mock_is_private, mock_admin):
        mock_admin.return_value = True
        mock_is_private.return_value = True
        self.mock_event.payload = "user@example.com secretpassword"
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        self.mock_bot.rpc.add_or_update_transport.assert_called_once_with(
            self.accid, {"addr": "user@example.com", "password": "secretpassword"}
        )
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Backup transport `user@example.com` added", msg_text)

    @patch("commands._is_dc_admin")
    @patch("commands._is_private_chat")
    def test_addtransport_sanitized_error(self, mock_is_private, mock_admin):
        mock_admin.return_value = True
        mock_is_private.return_value = True
        self.mock_event.payload = "DCACCOUNT:bad"
        self.mock_bot.rpc.add_transport_from_qr.side_effect = RuntimeError("Internal secret connection failure")
        commands.addtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertEqual(msg_text, "❌ Failed to add transport.")

    # ── /rmtransport ───────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_rmtransport_non_admin_rejected(self, mock_admin):
        mock_admin.return_value = False
        commands.rmtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("only for the administrator", msg_text)

    @patch("commands._is_dc_admin")
    def test_rmtransport_cannot_remove_last(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "relay@example.com"
        self.mock_bot.rpc.list_transports.return_value = [{"addr": "relay@example.com"}]
        commands.rmtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Cannot remove the last transport", msg_text)

    @patch("commands._is_dc_admin")
    def test_rmtransport_not_found(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "nonexistent@example.com"
        self.mock_bot.rpc.list_transports.return_value = [
            {"addr": "relay1@example.com"},
            {"addr": "relay2@example.com"},
        ]
        commands.rmtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("not found", msg_text)

    @patch("commands._is_dc_admin")
    def test_rmtransport_success(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "relay2@example.com"
        self.mock_bot.rpc.list_transports.return_value = [
            {"addr": "relay1@example.com"},
            {"addr": "relay2@example.com"},
        ]
        commands.rmtransport_command(self.mock_bot, self.accid, self.mock_event)
        self.mock_bot.rpc.delete_transport.assert_called_once_with(self.accid, "relay2@example.com")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("removed", msg_text)

    @patch("commands._is_dc_admin")
    def test_rmtransport_sanitized_error(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "relay2@example.com"
        self.mock_bot.rpc.list_transports.side_effect = RuntimeError("DB locked")
        commands.rmtransport_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertEqual(msg_text, "❌ Failed to remove transport.")

    # ── /setprimary ────────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_setprimary_success(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "primary@example.com"
        self.mock_bot.rpc.list_transports.return_value = [{"addr": "primary@example.com"}]
        commands.setprimary_command(self.mock_bot, self.accid, self.mock_event)
        self.mock_bot.rpc.set_config.assert_called_once_with(self.accid, "configured_addr", "primary@example.com")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Primary SMTP transport switched", msg_text)

    @patch("commands._is_dc_admin")
    def test_setprimary_sanitized_error(self, mock_admin):
        mock_admin.return_value = True
        self.mock_event.payload = "primary@example.com"
        self.mock_bot.rpc.list_transports.return_value = [{"addr": "primary@example.com"}]
        self.mock_bot.rpc.set_config.side_effect = RuntimeError("Config write failed")
        commands.setprimary_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertEqual(msg_text, "❌ Failed to set primary transport.")

    # ── /resilient ─────────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_resilient_toggle(self, mock_admin):
        mock_admin.return_value = True

        # Toggle to ON
        self.mock_event.payload = ""
        commands.resilient_command(self.mock_bot, self.accid, self.mock_event)
        self.assertEqual(database.get_config("resilient"), "1")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("ENABLED", msg_text)

        # Toggle to OFF
        self.mock_event.payload = ""
        commands.resilient_command(self.mock_bot, self.accid, self.mock_event)
        self.assertEqual(database.get_config("resilient"), "0")
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("DISABLED", msg_text)

        # Set explicitly ON
        self.mock_event.payload = "on"
        commands.resilient_command(self.mock_bot, self.accid, self.mock_event)
        self.assertEqual(database.get_config("resilient"), "1")

        # Set explicitly OFF
        self.mock_event.payload = "off"
        commands.resilient_command(self.mock_bot, self.accid, self.mock_event)
        self.assertEqual(database.get_config("resilient"), "0")

    # ── /transports ────────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_transports_list_success(self, mock_admin):
        mock_admin.return_value = True
        self.mock_bot.rpc.list_transports.return_value = [{"addr": "relay1@example.com"}]
        commands.transports_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Configured Transports", msg_text)
        self.assertIn("relay1@example.com", msg_text)

    @patch("commands._is_dc_admin")
    def test_transports_sanitized_error(self, mock_admin):
        mock_admin.return_value = True
        self.mock_bot.rpc.list_transports.side_effect = RuntimeError("Internal RPC error")
        commands.transports_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertEqual(msg_text, "❌ Failed to list transports.")

    # ── /stats ─────────────────────────────────────────────────────────────

    @patch("commands._is_dc_admin")
    def test_stats_command(self, mock_admin):
        mock_admin.return_value = True
        commands.stats_command(self.mock_bot, self.accid, self.mock_event)
        msg_text = self.mock_bot.rpc.send_msg.call_args[0][2].text
        self.assertIn("Bot Statistics", msg_text)
        self.assertIn("Total Registered Usernames", msg_text)


class TestHelpPrivateReply(unittest.TestCase):
    """Plain /help in a group goes to the sender privately; /help@<bot> stays in the group."""

    def _msg(self, text):
        msg = MagicMock()
        msg.text = text
        msg.chat_id = 42
        msg.from_id = 7
        return msg

    def _bot(self):
        mock_bot = MagicMock()
        mock_bot.rpc.create_chat_by_contact_id.return_value = 555
        return mock_bot

    @patch("commands._is_private_chat", return_value=False)
    def test_plain_help_in_group_goes_private(self, _mock_chat):
        mock_bot = self._bot()
        self.assertEqual(commands._get_help_chat_id(mock_bot, 1, self._msg("/help")), 555)
        mock_bot.rpc.create_chat_by_contact_id.assert_called_once_with(1, 7)

    @patch("commands._is_private_chat", return_value=False)
    def test_addressed_help_in_group_stays_in_group(self, _mock_chat):
        mock_bot = self._bot()
        self.assertEqual(commands._get_help_chat_id(mock_bot, 1, self._msg("/help@username extra")), 42)
        mock_bot.rpc.create_chat_by_contact_id.assert_not_called()

    @patch("commands._is_private_chat", return_value=True)
    def test_plain_help_in_private_chat_stays(self, _mock_chat):
        mock_bot = self._bot()
        self.assertEqual(commands._get_help_chat_id(mock_bot, 1, self._msg("/help")), 42)
        mock_bot.rpc.create_chat_by_contact_id.assert_not_called()

    @patch("commands._is_private_chat", return_value=False)
    @patch("commands._dc_send_msg_with_stats")
    @patch("commands.MsgData", side_effect=lambda text: text)
    @patch("commands.get_help_text", return_value="HELP")
    def test_help_command_in_group_sends_private_with_note(self, _mock_text, _mock_msgdata, mock_send, _mock_chat):
        mock_bot = self._bot()
        event = MagicMock()
        event.msg = self._msg("/help")
        commands.help_command(mock_bot, 1, event)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[0][2], 555)
        self.assertIn("/help@username", mock_send.call_args[0][3])


class TestCommandSuffixParser(unittest.TestCase):
    """/cmd@<suffix> is only handled when the suffix addresses this bot."""

    def _run(self, text):
        mock_bot = MagicMock()
        mock_bot.rpc.get_contact.return_value.address = "usernamebot@chatmail.uk"
        seen = []

        def original(accid, event):
            seen.append(event.msg.text)
            event.command = event.msg.text.split()[0]

        mock_bot._parse_command = original
        dc_helpers.setup_custom_command_parser(mock_bot, ["user", "usernamebot"])
        event = MagicMock()
        event.msg = MagicMock()
        event.msg.text = text
        event.msg.__setitem__ = lambda _self, key, value: setattr(event.msg, key, value)
        mock_bot._parse_command(1, event)
        return event, seen

    def test_own_suffix_is_stripped_and_handled(self):
        event, seen = self._run("/help@username")
        self.assertEqual(seen, ["/help"])
        self.assertEqual(event.command, "/help")
        self.assertEqual(event.msg.text, "/help@username")

    def test_other_bot_suffix_is_ignored(self):
        event, seen = self._run("/help@yt")
        self.assertEqual(seen, [])
        self.assertEqual(event.command, "")


if __name__ == "__main__":
    unittest.main()
