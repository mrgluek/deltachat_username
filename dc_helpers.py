import json
import os
import re
from typing import Optional

from deltachat2 import MsgData

import database


def configure_bot_profile(bot, accid: int):
    """Configure bot display name, status text, and avatar icon from environment or default files."""
    try:
        bot_name = os.environ.get("DISPLAY_NAME")
        if not bot_name and os.path.exists("/data/options.json"):
            try:
                with open("/data/options.json", "r", encoding="utf-8") as f:
                    opts = json.load(f)
                    bot_name = opts.get("display_name", "").strip()
            except Exception:
                pass
        if not bot_name:
            bot_name = "Username Bot"
        bot.rpc.set_config(accid, "displayname", bot_name)
    except Exception as e:
        bot.logger.warning(f"Failed to set displayname: {e}")

    try:
        status_text = os.environ.get("STATUS_TEXT")
        if not status_text and os.path.exists("/data/options.json"):
            try:
                with open("/data/options.json", "r", encoding="utf-8") as f:
                    opts = json.load(f)
                    status_text = opts.get("status_text", "").strip()
            except Exception:
                pass
        if not status_text:
            status_text = "Short custom invite link service for Delta Chat: https://d.gluek.info"
        bot.rpc.set_config(accid, "selfstatus", status_text)
    except Exception as e:
        bot.logger.warning(f"Failed to set selfstatus: {e}")

    try:
        avatar_env = os.environ.get("AVATAR_PATH")
        avatar_paths = []
        base_dir = os.path.dirname(os.path.abspath(__file__))

        if avatar_env:
            if os.path.isabs(avatar_env):
                avatar_paths.append(avatar_env)
            else:
                avatar_paths.append(os.path.join(base_dir, avatar_env))
                avatar_paths.append(os.path.abspath(avatar_env))

        avatar_paths.extend(
            [
                os.path.join(base_dir, "icon.png"),
                os.path.join(base_dir, "icon.jpg"),
                os.path.join(base_dir, "icon.jpeg"),
            ]
        )

        for path in avatar_paths:
            if os.path.exists(path):
                bot.rpc.set_config(accid, "selfavatar", path)
                bot.logger.info(f"Avatar set from {path}")
                break
    except Exception as e:
        bot.logger.warning(f"Failed to set selfavatar: {e}")


def is_group_chat(bot, accid: int, chat_id: int) -> bool:
    """
    Determine if a chat is a group chat using Delta Chat RPC basic info,
    full chat info, and chat contacts fallback. Matches standard implementation across all repository bots.
    """
    # 1. Primary check: get_basic_chat_info
    try:
        chat_info = bot.rpc.get_basic_chat_info(accid, chat_id)
        if chat_info:
            if isinstance(chat_info, dict):
                chat_type = chat_info.get("chat_type") or chat_info.get("chatType")
                type_val = chat_info.get("type")
            else:
                chat_type = getattr(chat_info, "chat_type", None) or getattr(chat_info, "chatType", None)
                type_val = getattr(chat_info, "type", None)

            if chat_type is not None:
                if str(chat_type).lower() in ("group", "verifiedgroup", "channel"):
                    return True
                if str(chat_type).lower() == "single":
                    return False

            if type_val is not None:
                if str(type_val) in ("100", "120", "130"):
                    return True
                if str(type_val) in ("1", "single"):
                    return False
    except Exception as e:
        bot.logger.debug(f"get_basic_chat_info failed for chat {chat_id}: {e}")

    # 2. Secondary check: get_full_chat_by_id
    try:
        chat_info = bot.rpc.get_full_chat_by_id(accid, chat_id)
        if chat_info:
            if isinstance(chat_info, dict):
                chat_type = chat_info.get("chat_type") or chat_info.get("chatType")
                type_val = chat_info.get("type")
            else:
                chat_type = getattr(chat_info, "chat_type", None) or getattr(chat_info, "chatType", None)
                type_val = getattr(chat_info, "type", None)

            if chat_type is not None:
                if str(chat_type).lower() in ("group", "verifiedgroup", "channel"):
                    return True
                if str(chat_type).lower() == "single":
                    return False

            if type_val is not None:
                if str(type_val) in ("100", "120", "130"):
                    return True
                if str(type_val) in ("1", "single"):
                    return False
    except Exception as e:
        bot.logger.debug(f"get_full_chat_by_id failed for chat {chat_id}: {e}")

    # 3. Tertiary fallback: get_chat_contacts length check
    try:
        contacts = bot.rpc.get_chat_contacts(accid, chat_id)
        if isinstance(contacts, list):
            if len(contacts) > 1:
                return True
            if len(contacts) == 1:
                return False
    except Exception as e:
        bot.logger.debug(f"get_chat_contacts failed for chat {chat_id}: {e}")

    return False


def setup_custom_command_parser(bot, allowed_prefixes):
    original_parse_command = bot._parse_command

    def custom_parse_command(accid: int, event) -> None:
        text = event.msg.text
        if not text:
            original_parse_command(accid, event)
            return

        parts = text.split(maxsplit=1)
        cmd = parts[0]
        
        if "@" in cmd:
            cmd_name, suffix = cmd.split("@", 1)
            suffix_lower = suffix.lower()
            
            if suffix_lower:
                try:
                    self_address = bot.rpc.get_contact(accid, 1).address.lower()
                except Exception:
                    self_address = ""
                
                matched = False
                for p in allowed_prefixes:
                    if suffix_lower.startswith(p.lower()) or p.lower().startswith(suffix_lower):
                        matched = True
                        break
                if not matched and self_address and suffix_lower == self_address:
                    matched = True
                
                if matched:
                    new_text = cmd_name
                    if len(parts) > 1:
                        new_text += " " + parts[1]
                    
                    original_text = event.msg.text
                    event.msg["text"] = new_text
                    try:
                        original_parse_command(accid, event)
                    finally:
                        event.msg["text"] = original_text
                else:
                    event.command = ""
                    event.payload = ""
            else:
                original_parse_command(accid, event)
        else:
            original_parse_command(accid, event)
            
            # /help is not suppressed: plain /help in a group is answered privately (see help_command)
            if event.command == "/stats":
                try:
                    chat = bot.rpc.get_chat(accid, event.msg.chat_id)
                    is_group = getattr(chat, "chat_type", "Single") != "Single"
                except Exception:
                    is_group = False
                
                if is_group:
                    try:
                        contacts = bot.rpc.get_chat_contacts(accid, event.msg.chat_id)
                        bot_count = 0
                        for contact_id in contacts:
                            if contact_id == 1:
                                bot_count += 1
                                continue
                            c = bot.rpc.get_contact(accid, contact_id)
                            if getattr(c, "is_bot", False):
                                bot_count += 1
                                if bot_count > 1:
                                    break
                        if bot_count > 1:
                            event.command = ""
                            event.payload = ""
                    except Exception:
                        pass

    bot._parse_command = custom_parse_command


def _is_private_chat(bot, accid: int, chat_id: int) -> bool:
    """Check if the given chat is a 1:1 private chat."""
    return not is_group_chat(bot, accid, chat_id)


def _is_dc_admin(bot, accid: int, from_id: int) -> bool:
    """Check whether a contact is an authorized administrator."""
    admin_email = database.get_admin_email()
    admin_fp = database.get_admin_fingerprint()

    if not admin_email and not admin_fp:
        return False

    try:
        contact = bot.rpc.get_contact(accid, from_id)
        if admin_email and contact.address and contact.address.lower() == admin_email.lower():
            # Auto-upgrade: if fingerprint became available after initial email setup, save it now!
            if not admin_fp:
                fp = _get_contact_fingerprint(bot, accid, from_id, contact=contact)
                if fp:
                    first_fp = fp.split(",")[0].strip().upper()
                    database.set_admin_fingerprint(first_fp)
            return True
    except Exception:
        pass

    try:
        fp = _get_contact_fingerprint(bot, accid, from_id)
        if admin_fp and fp and admin_fp.upper() in [f.upper() for f in fp.split(",")]:
            return True
    except Exception:
        pass

    return False


def _get_contact_fingerprint(bot, accid: int, contact_id: int, contact=None) -> Optional[str]:
    """Retrieve contact's cryptographic PGP fingerprint from Delta Chat RPC, filtering out bot self-fingerprints."""
    self_fps = set()
    try:
        bot_addrs = []
        bot_addr = bot.rpc.get_config(accid, "addr")
        if bot_addr:
            bot_addrs.append(bot_addr.lower().strip())

        try:
            transports = bot.rpc.list_transports(accid)
            for t in transports:
                t_addr = t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "")
                if t_addr:
                    bot_addrs.append(t_addr.lower().strip())
        except Exception:
            pass

        if bot_addrs:
            for args in [(accid, contact_id), (contact_id,)]:
                try:
                    enc_info_self = bot.rpc.get_contact_encryption_info(*args)
                    if enc_info_self:
                        blocks = re.split(r"\n\s*\n", enc_info_self.strip())
                        for block in blocks:
                            if any(a in block.lower() for a in bot_addrs):
                                matches = re.findall(
                                    r"[0-9a-fA-F]{32,64}", "".join(block.split()).replace(":", "")
                                )
                                self_fps.update(m.upper() for m in matches)
                        break
                except Exception:
                    continue
    except Exception as e:
        bot.logger.error(f"Error detecting self-fingerprint: {e}")

    # 1. Try directly from contact object if available
    if contact:
        get_val = getattr(contact, "get", lambda k: getattr(contact, k, None))
        for attr in ["fingerprint", "key_fingerprint", "public_key"]:
            val = get_val(attr)
            if val:
                matches = re.findall(r"[0-9a-fA-F]{32,64}", str(val).replace(" ", "").replace(":", ""))
                valid_matches = [m.upper() for m in matches if m.upper() not in self_fps]
                if valid_matches:
                    return ",".join(valid_matches)

    # 2. Try get_contact_config(accid, contact_id, "fp")
    try:
        fp = bot.rpc.get_contact_config(accid, contact_id, "fp")
        if fp:
            clean_fp = fp.upper().replace(" ", "").replace(":", "")
            if clean_fp not in self_fps and re.match(r"^[0-9A-F]{32,64}$", clean_fp):
                return clean_fp
    except Exception:
        pass

    # 3. Try get_contact_encryption_info
    for args in [(accid, contact_id), (contact_id,)]:
        try:
            enc_info = bot.rpc.get_contact_encryption_info(*args)
            if enc_info:
                cleaned_info = "".join(enc_info.split()).replace(":", "")
                matches = re.findall(r"[0-9a-fA-F]{32,64}", cleaned_info)
                valid_matches = [m.upper() for m in matches if m.upper() not in self_fps]
                if valid_matches:
                    return ",".join(valid_matches)
        except Exception as e:
            bot.logger.debug(f"get_contact_encryption_info{args} failed: {e}")
            continue

    return None


def _dc_send_msg_with_stats(bot, accid: int, chat_id: int, msg_data: MsgData):
    """Send a message via Delta Chat RPC and update sent statistics."""
    bot.rpc.send_msg(accid, chat_id, msg_data)
    try:
        addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr")
        if addr:
            database.increment_transport_sent(addr)
    except Exception:
        pass
