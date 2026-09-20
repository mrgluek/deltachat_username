#!/usr/bin/env python3
import io
import os
import sys
import threading
import time

import uvicorn

import database
from web.routes import app
from security import (
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    CRAWLER_USER_AGENTS,
    TELEGRAM_IP_PREFIXES,
    get_client_ip,
    is_rate_limited,
    clear_rate_limits,
    is_crawler_request,
)
from formatting import (
    BASE_URL,
    get_request_base_url,
    format_username_card_text,
    get_invite_base_url,
    rewrite_invite_link,
    validate_username_format,
    validate_invite_link,
    extract_invite_link,
    generate_qr_data_uri,
)
from dc_helpers import (
    configure_bot_profile,
    is_group_chat,
    _is_private_chat,
    _is_dc_admin,
    _get_contact_fingerprint,
    _dc_send_msg_with_stats,
)

try:
    import qrcode
except ImportError:
    qrcode = None

from commands import (
    VERSION,
    dc_cli,
    get_help_text,
    help_command,
    donate_command,
    initadmin_command,
    username_command,
    link_command,
    unlink_command,
    on_new_message,
    url_command,
    inviteurl_command,
    _setup_resilient_mode,
    on_msg_failed,
    stats_command,
    transports_command,
    addtransport_command,
    rmtransport_command,
    setprimary_command,
    resilient_command,
)


# --- LIFECYCLE HOOKS ---


def run_fastapi(host: str = "0.0.0.0", port: int = 8080):
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


@dc_cli.on_init
def on_init(bot, _args):
    port = int(os.getenv("PORT", "8080"))
    web_thread = threading.Thread(target=run_fastapi, kwargs={"port": port}, daemon=True)
    web_thread.start()

    accounts = bot.rpc.get_all_account_ids()
    for accid in accounts:
        configure_bot_profile(bot, accid)


@dc_cli.on_start
def on_start(bot, _args):
    bot.logger.info(f"🚀 Delta Chat Username Bot v{VERSION} is now fully running. Waiting for events...")
    _setup_resilient_mode(bot)

    def _bg_cleanup_worker():
        while True:
            try:
                time.sleep(60)
                database.flush_transport_stats()
                database.cleanup_old_records()
            except Exception as e:
                bot.logger.error(f"Error in background cleanup worker: {e}")

    threading.Thread(target=_bg_cleanup_worker, daemon=True).start()

    accounts = bot.rpc.get_all_account_ids()
    if accounts:
        accid = accounts[0]
        configure_bot_profile(bot, accid)

        admin_email = database.get_admin_email()
        admin_fp = database.get_admin_fingerprint()
        if admin_email:
            fp_suffix = f" ({admin_fp[-8:].upper()})" if admin_fp else ""
            print(f"👑 Bot Administrator: {admin_email}{fp_suffix}")

        try:
            addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr") or ""
            if addr:
                database.set_config("bot_addr", addr)
        except Exception:
            pass

        try:
            transports = bot.rpc.list_transports(accid)
            print("\n" + "=" * 50)
            print("📡 Configured Bot Transports (Relays):")
            for t in transports:
                t_addr = t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "")
                print(f" - {t_addr}")
        except Exception:
            pass

        try:
            qrdata = bot.rpc.get_chat_securejoin_qr_code(accid, None)
            qrdata = rewrite_invite_link(qrdata)
            database.set_config("bot_invite_url", qrdata)
            print("\nTo add this bot, scan the QR code or copy the link below:\n")

            if qrcode:
                qr = qrcode.QRCode(version=1, box_size=1, border=2)
                qr.add_data(qrdata)
                qr.make(fit=True)
                f = io.StringIO()
                qr.print_ascii(out=f)
                print(f.getvalue())

            print(qrdata)
            print("\n" + "=" * 50 + "\n")
        except Exception as e:
            bot.logger.error(f"Failed to generate QR code: {e}")


# --- MAIN RUNNER ---


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("serve")
    dc_cli.start()
