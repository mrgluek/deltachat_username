# Changelog

All notable changes to the **Delta Chat Username Bot (`deltachat_username`)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.18.0] - 2026-10-29

### Fixed
- **"Linked" Shows the Claim Date Again**: The card, web pages and social previews showed the time the record last changed as "Linked", so every contact sync (v1.16.0) that rewrote a personal link reset it to the sync time. Claims now keep a separate `linked_at`, set by `/link`; contact sync only moves `updated_at`. Re-linking the same name from the same chat keeps the original date; a new name or a takeover by another chat starts a new one.

### Added
- **"Updated" Date**: When the link changed after it was claimed, the chat card, `/{username}` preview text and the `/{username}/card` page show `🔄 Updated: …` next to `📅 Linked: …`. The PNG/SVG cards show only the claim date.

### Changed
- **Database**: New `linked_at` column in `usernames`, added on startup. Existing claims take it from `updated_at`, so claims synced before this release show their last sync date as the claim date.

## [1.17.0] - 2026-10-28

### Changed
- **Delta Chat Core 2.66.0**: `deltachat-rpc-server` is pinned to 2.66.0 (was 2.65.0). Core 2.66 removes the `configured_addr` config: `get_config("configured_addr")` now fails with "unknown key", and `addr` has been empty since core 2.61. The bot's own address now comes from its self contact (`dc_fingerprint.get_self_addr()`), which the core fills from the primary relay; this also works on older cores.

## [1.16.1] - 2026-10-28

### Security
- **Admin Check No Longer Fooled by a Display Name**: The contact's key fingerprint was found by searching the whole `get_contact_encryption_info()` text for hex strings, including the line with the contact's display name, so a contact named `x<admin fingerprint>x` passed the admin check. The fingerprint is now read only from the lines under each key header, and the bot's own key is recognised by the fingerprint in its invite link instead of by its address. When the keys cannot be told apart the check fails instead of guessing. The code is in `dc_fingerprint.py`, shared verbatim between the bots.

### Changed
- **Ready for the Core 2.66 Fingerprint Format**: Core 2.66 prints `Me:` instead of `Me (address):` and sorts the key blocks by fingerprint, so finding a key block by address stops working. The new parser handles both formats.
- **Invite Link Sync Matches Keys, Not Addresses**: Contact sync picked the contact's key by its address in the encryption info; it now uses the same parser.
- **Core Pinned to 2.65.0**: `deltachat-rpc-server` was `>=2.62.0`, so any image rebuild pulled core 2.66.0, which removes the `configured_addr` option the bot still reads. Core upgrades are now made on purpose, after reading the core changelog.

## [1.16.0] - 2026-10-27

### Added
- **Relay sync (`r=`)**: personal invite links now carry the owner's full relay list. The bot reads it from the contact's key (`get_contact_encryption_info`, "Relays:"), keeps `a=` on the current address when it is still listed (else the first relay) and puts the other relays (up to 5 in all, as the core reads) into `r=`.
- **Hourly contact sync**: relay changes arrive as core keyupdate messages (core 2.60+), which the core trashes without a message event, so the bot now also re-checks every personal link once an hour (new `contact_sync.py`, first run 2 minutes after start). It only reads the core's local data, no network requests.

### Fixed
- **Links are only synced with their own key**: the sync now compares the contact's fingerprint with the link's. A link registered for another profile or another person is no longer rewritten with the sender's address and name.
- **Address sync never worked**: the old code read `contact.addr`, but the RPC contact field is `address`, so only the name was ever updated.
- **`n=` no longer becomes an address**: the name is taken from the name the contact set (`auth_name`), not from `display_name`, which falls back to the address.
- **`r=` kept intact**: rewriting a link whose `r=` lists several relays encoded the separating commas as `%2C`. The core splits `r=` on raw commas, so the result was one invalid address. Each address is now encoded on its own.

## [1.15.1] - 2026-10-27

### Security
- **HTML/SVG escaping on the web pages**: the profile page (`/<name>`), the `/card` page, the 404 page and the `/og.svg` card inserted names, e-mail, the invite link and the requested path into the page without escaping. A group name like `"><script>…` registered with `/link`, or a crafted URL such as `/<img src=x onerror=…>` on the 404 page, ran script on the site's domain. All such values are now HTML-escaped (XML-escaped in the SVG), and the redirect script gets the invite link as a JSON string literal. A name with `&` no longer breaks the SVG/PNG card either.

### Changed
- **"Open in ArcaneChat" opens the app directly**: for ArcaneChat admin-group links, the button on the profile page and on `/card` now uses an `openpgp4fpr:FINGERPRINT#v=3&…&z=…` URI instead of `https://i.delta.chat/#…`, so the installed ArcaneChat app opens the invite without the i.delta.chat page in between (which offers Delta Chat, which can't join these groups). The `/card` QR code keeps the `https` link, which ArcaneChat scans fine.

## [1.15.0] - 2026-10-27

### Added
- **ArcaneChat Admin Groups**: Invite links with the `z=` group-name parameter (ArcaneChat admin groups) are recognised as groups and flagged `arcanechat_only`. The chat card, the `/link` reply, the OpenGraph description and the SVG/PNG cards say "ArcaneChat only"; the web page no longer auto-redirects such links, shows a notice with a link to https://arcanechat.me and an "Open in ArcaneChat" button; `GET /api/username/<name>` has a new additive `arcanechat_only` field (`type` stays `group`).

### Fixed
- ArcaneChat admin-group links were classified as `contact` (shown as the inviter's email). Because of that, `update_invite_link_contact_info` could rewrite their `a=`/`n=` with the sender's address and name; links with `z=` are now never modified.

## [1.14.1] - 2026-10-26

### Changed
- **Download Limit 64 KB**: Photos, videos and files over 64 KB sent to the bot are no longer downloaded automatically (the bot only reads commands), saving traffic and disk space. Plain text and small attachments arrive as before.

## [1.14.0] - 2026-10-24

### Added
- **Automatic Account Creation**: `serve` without a configured account no longer exits with "There are no configured accounts to serve". The bot asks the core (`init_transports`, core 2.62+) to create an account on the fastest chatmail relay of its built-in list; the core adds further relays in the background. If that fails, the error is logged, `serve` exits and the container restart retries. `bot.py init <addr> <password>` and `bot.py init DCACCOUNT:server.tld` still choose the account explicitly.

### Changed
- **The server runs releases, not the tip of `main`.** `update.sh` deploys the newest `vX.Y.Z` tag, so a merge into `main` reaches the server only once it is released; several PRs can go out together. `UPDATE_REF` in `.env.local` pins a release (`UPDATE_REF=v1.13.0` - a rollback; empty again = newest) or follows a branch as before (`UPDATE_REF=main`). A release tag moved on GitHub or Forgejo makes the update fail instead of deploying the changed code. Errors that stopped the script with a message (both remotes unreachable, an unknown `UPDATE_REF`) now also ping the healthcheck's `/fail`, not only failed commands. The script now runs as one function, so the `git reset` that rewrites `update.sh` cannot confuse the running copy.
- **Releases are published by a tag** (new `.github/workflows/release.yml`): pushing `vX.Y.Z` checks that `commands.py` has that version, creates the GitHub release with the version's section of this file as its notes (an existing release is left alone), then sends the ntfy notification and the `bot-updated` dispatch to `hass-addons-deltachat` (now with `"version"` in the payload). Both used to go out on every push to `main` (`username-changelog.yml`, removed), so Home Assistant users got unreleased code.
- **README**: the "Configure Email and Admin" deployment step is optional now; new "Updates" section on `update.sh`, `UPDATE_REF` and releasing.
- Releasing: merge, then `git tag -a vX.Y.Z -m "..." <commit> && git push origin vX.Y.Z`.
- **Upgrading:** tag `v1.14.0` right after merging this. Until then the new `update.sh` would deploy `v1.13.0`, which still has the old script that follows `main` - and the server would switch back and forth on every run.

## [1.13.0] - 2026-10-16

### Added
- **MIT License**: the project is now licensed under MIT (`LICENSE`).
- **Invite Link in the Lookup API**: `GET /api/username/<name>` now also returns `invite_link`, the invite on `i.delta.chat` (the same link `/username` sends as the card caption; mirror domains such as `i.deltachat.id` are turned into `i.delta.chat`). Delta Chat apps open it directly, while the short link `url` goes through the browser first. Like `/username` and the profile page, it contains the address and fingerprint the user published.

## [1.12.0] - 2026-10-16

### Added
- **Lookup API for Bots (`GET /api/username/<name>`)**: JSON with the username, its type (`contact`, `group` or `channel`), display name and short link (`https://deltachat.id/<name>`); 404 `{"error": "not_found"}` for a name nobody claimed. Bouncer Bot uses it for `@mentions` of people who are not in a group. Unlike the profile page it returns no email address or fingerprint. Requests count against the same limit as profile pages (10 per minute per IP, 429 `{"error": "rate_limited"}`). Other bots cannot use `/username` for this: deltabot-cli ignores messages from bots, and the answer would arrive asynchronously.

## [1.11.0] - 2026-10-14
- **`/transports` Shows the Relay Actually Used for Sending**: Since core 2.61 the core sends through the relay that last worked and switches only when it cannot connect, so the main address (`configured_addr`) says nothing about where mail goes out. `/transports` now lists relays in the order the core tries them, with the current sending relay first, shows the core's send queue (waiting messages and retries) and outgoing status, and per relay the incoming status, when the last message arrived, mailbox storage usage (⚠️ from 80%) and when it was added. The sending order and queue are read from the core's account database (read-only); the report is built by the shared `transports_view.py`.
- **Removed Misleading Per-Relay Sent/Received Counters**: They credited every message to `configured_addr` (or, in some places, the wrong address), so the numbers and "last sent" dates were wrong once the core sent through another relay. Counting them also cost extra RPC calls per message. The `transport_stats` table is left in place but no longer updated.

## [1.10.0] - 2026-09-28

### Removed
- **Bot-Side Relay Failover**: Removed the `MSG_FAILED` failover handler and the resilient-send `send_msg` patch. Both switched `configured_addr` and called `resend_messages`, but since Delta Chat core 2.61 the SMTP relay is no longer chosen by `configured_addr`: the core tries the newest relay first and falls back to the next one if a relay is unreachable. The old logic could no longer switch relays and only caused delayed duplicate resends.

### Changed
- **`/setprimary` and `/resilient` Deprecated**: Both commands are disabled and only reply with an explanation of how the core picks relays now. They are removed from `/help` and the README.
- **`/transports` Sending Order**: Relays are listed newest first, in the order the core tries them for sending, instead of marking `configured_addr` as "Used for sending".
- **Core Requirement**: `requirements.txt` now requires `deltachat-rpc-server>=2.62.0`.

## [1.9.0] - 2026-09-24

### Added
- **Target-Specific Commands in Group Chats**: Commands can be addressed to this bot with a suffix (`/help@username`, `/stats@user`, …); commands addressed to another bot (`/help@yt`) are ignored. Un-suffixed `/stats` is ignored in groups with several bots.

### Changed
- **Private `/help` in Groups**: A plain `/help` sent in a group chat is now answered in a private 1:1 chat with the sender instead of the group, so several bots don't flood it with help texts (the reply ends with a note on how to show it in the group). Addressed `/help@username` is still answered in the group.

## [1.8.6] - 2026-09-24

### Fixed
- **`update.sh` Deployed the Wrong Branch**: Branch detection took the first remote branch in alphabetical order, so a leftover PR branch such as `origin/claude/...` sorted before `origin/master` and was deployed instead (and new `master` commits were reported as "Already up to date"). It now follows the checked-out branch, falling back to `main`/`master`.

## [1.8.5] - 2026-09-20

### Refactor
- **Modularized `bot.py`**: Split the 2100+ line monolith into `security.py` (rate limiting, crawler detection), `formatting.py` (invite-link/URL helpers, QR generation), `dc_helpers.py` (Delta Chat RPC helpers: profile config, group-chat detection, admin/fingerprint checks), `web/routes.py` (FastAPI app and all HTTP endpoints), and `commands.py` (all bot command/event handlers). `bot.py` is now just the assembly/entrypoint file (`run_fastapi`, `on_init`, `on_start`, `__main__`) and keeps re-exporting the same names, so the Docker entrypoint (`python bot.py serve`) and existing imports are unaffected. Pure move, no behavior change; verified with the full test suite after every extracted module.

### Security
- **Fixed spoofable rate-limit bypass**: `get_client_ip` now trusts the *last* entry of `X-Forwarded-For` (the one our reverse proxy appends) instead of the first (client-supplied) one, closing a bypass where any client could fake its own IP via the header to dodge the per-IP rate limiter.
- **Bounded rate-limit memory**: Added `prune_rate_limits()`, run periodically alongside the existing background cleanup worker, so `_ip_request_history` no longer grows unbounded for IPs that stop returning.
- Removed unused `is_crawler_request`/`CRAWLER_USER_AGENTS`/`TELEGRAM_IP_PREFIXES` dead code left over from a previous implementation.

---

## [1.8.4] - 2026-09-16

### Security
- **Web Endpoint Rate Limiting**: Added sliding-window per-IP rate limiting to root homepage (`GET /`) and username card view (`GET /{username}/card`) with HTTP 429 `Retry-After: 60` response headers.
- **Dependency Pinning**: Pinned `fastapi>=0.100.0,<1.0.0`, `uvicorn>=0.22.0,<1.0.0`, `requests>=2.28.0,<3.0.0`, `httpx>=0.24.0,<1.0.0`, `qrcode>=7.4.2,<8.0.0`, `pillow>=10.4.0,<11.0.0`, and `resvg-py>=0.4.0,<1.0.0` in `requirements.txt`.

---

## [1.8.3] - 2026-09-09

### Security & Hardening
- **Private Chat Enforcement**: Enforced `_is_private_chat` on sensitive commands `/initadmin` and `/addtransport`, preventing credentials or admin claiming from leaking inside group chats.
- **Error Sanitization**: Sanitized user-facing error messages in transport administration commands (`/addtransport`, `/rmtransport`, `/setprimary`, `/transports`, `/resilient`), logging detailed diagnostics to server logs while replying with safe generic notices.
- **Resilient Sending Mode**: Added `_setup_resilient_mode(bot)` and `resilient_lock = threading.Lock()` with automatic failover transport resending and temporary primary address fallback restoration under `try...finally`.
- **Automatic Message Failover**: Added `on_msg_failed` handler with exponential backoff resend across configured mail relays.

### Performance & Concurrency
- **SQLite WAL & Concurrency**: Enabled WAL journal mode (`PRAGMA journal_mode = WAL`), `synchronous = NORMAL`, and `busy_timeout = 5000` via `get_connection()`.
- **Resource Cleanup**: Ensured all database connections strictly adhere to `try...finally: conn.close()`, resolving database connection leaks.
- **Buffered Transport Statistics**: Implemented in-memory write buffer (`_transport_stats_buffer` with `_transport_stats_lock`) and periodic background flushing (`flush_transport_stats`), slashing disk I/O under high traffic.
- **Automated Retention Worker**: Added background daemon worker in `on_start` running periodic stats flushing and expired pending claim cleanups (`cleanup_old_records`).
- **Comprehensive Test Suite**: Added `tests/test_database.py` and `tests/test_transport_commands.py` with 100% pass rate.

---

## [1.8.2] - 2026-09-07

### Added
- **Options.json Fallback for Display Name & Status Text**:
  - `configure_bot_profile` now checks `/data/options.json` fallback when `DISPLAY_NAME` or `STATUS_TEXT` are not set in environment variables.

---

## [1.8.1] - 2026-08-22

### Fixed
- **Admin Channel & Personal Profile Multi-Claim Isolation**:
  - Linking channel or broadcast invite links (`&b=`) in private chat now automatically stores claims under the `admin_<username>` namespace, preserving the admin's personal chat profile claim.
  - Automatically migrates existing channel claims out of the personal chat namespace when re-linking personal usernames (`/link gluek ...`), ensuring both `@stickers` and `@gluek` remain concurrently valid.

---

## [1.8.0] - 2026-08-22

### Added & Improved
- **Visual WebP Card Image Attachments in `/username`**:
  - Replaced monospace ASCII Unicode identicon text block in bot chat with an attached ~20KB WebP visual card image.
  - Accompanies the card with a clean, direct `https://i.delta.chat/#...` invite link as message caption, enabling one-tap native in-app chat start without external browser redirection.
  - Added `generate_og_webp_bytes` and `get_or_create_card_webp_path` in `identicon.py` with automatic fallback to text card if image rendering is unavailable.

---

## [1.7.0] - 2026-08-22

### Added
- **Automatic User Relay & Contact Details Synchronization**:
  - Whenever a registered user sends a message to the bot, the bot automatically checks their live contact info (`contact.addr` and `contact.display_name`) from Delta Chat core.
  - If the user changed their email relay / mail provider or updated their profile display name, the bot automatically updates their registered username invite link in the database and refreshes the cached OpenGraph verification cards (`update_invite_link_contact_info` & `update_username_invite_metadata`).
  - Personal invite link tokens and cryptographic signatures remain intact while keeping email address and display name 100% up to date.

---

## [1.6.2] - 2026-08-22

### Fixed & Improved
- **Universal OpenGraph 200 OK Delivery**:
  - Replaced conditional HTTP 307 redirect on `GET /{username}` with standard universal 200 OK delivery containing full OpenGraph and Twitter Card metadata alongside an instant client-side JavaScript redirect (`window.location.replace`).
  - Guarantees that all automated link previewers (Delta Chat WebPreview Bot, scrapers, messengers) receive complete OpenGraph metadata without being redirected to `i.deltachat.id`, regardless of the User-Agent used.

---

## [1.6.1] - 2026-08-22

### Fixed
- **WebPreviewBot & Link Preview Scraper Detection**:
  - Expanded crawler User-Agent recognition in `is_crawler_request` to include `webpreview`, `deltachat`, `requests`, `httpx`, `bot`, `preview`, `scraper`, and empty User-Agent clients.
  - Prevents Delta Chat `WebPreview Bot` and automated preview fetchers from following HTTP 307 redirects to `i.deltachat.id`, ensuring they receive full custom OpenGraph verification cards.

---

## [1.6.0] - 2026-08-22

### Added & Improved
- **Primary Domain `deltachat.id` & Dynamic Multi-Domain Support**:
  - Configured default base URL to `https://deltachat.id`.
  - Added dynamic request host detection (`get_request_base_url`) in web endpoints. The bot now automatically serves OpenGraph metadata, card previews, and SVG/PNG badges using whichever domain the client connected to (`deltachat.id` or `d.gluek.info`).
  - Updated `Caddyfile` with dual-domain reverse proxy (`deltachat.id, d.gluek.info`) and `www.deltachat.id` redirect.
  - Updated `docker-compose.yml`, `.env.example`, and `README.md`.

---

## [1.5.5] - 2026-08-22

### Fixed
- **Group & Channel Name Resolution**:
  - In group invite links (`&g=...`), prioritized group title over inviter's display name (`&n=...`).
  - In channel invite links (`&b=...`), prioritized broadcast title over sender's display name (`&n=...`).
  - Formatted verification cards to display `👥 Group: <Group Name>` and `📢 Channel: <Channel Name>` without displaying the inviter's personal email.

---

## [1.5.4] - 2026-08-21

### Fixed
- **Telegram IP Detection & OpenGraph Type**:
  - Added Telegram ASN IP prefix checking (`149.154.*`, `91.108.*`, `95.161.*`) in `is_crawler_request` for guaranteed crawler identification.
  - Switched `og:type` to `website` for universal summary card compatibility in Telegram and other chat platforms.

---

## [1.5.3] - 2026-08-21

### Fixed
- **Telegram & Messenger OpenGraph Card Unfurling**:
  - Removed `<meta http-equiv="refresh">` from the crawler HTML response. Previously, Telegram's WebPage crawler followed the meta-refresh target (`i.gluek.info`) instead of using the custom OpenGraph tags on `d.gluek.info`.
  - Added support for trailing slash URLs (`GET /{username}/`).

---

## [1.5.2] - 2026-08-21

### Fixed
- **Font Rendering in Docker Linux Environment**:
  - Added `fontconfig`, `fonts-dejavu`, `fonts-dejavu-core`, `fonts-liberation`, and `fonts-noto-color-emoji` to `Dockerfile`.
  - Configured explicit cross-platform font family fallbacks (`DejaVu Sans`, `Liberation Sans`) and font directory scanning (`/usr/share/fonts`, `/usr/share/fonts/truetype`) in `identicon.py`.
  - Fixed issue where minimal Debian Linux container lacked font files causing SVG text to be omitted during PNG rasterization.

---

## [1.5.1] - 2026-08-21

### Fixed & Improved
- **Pixel-Perfect PNG OpenGraph Cards (`resvg-py`)**:
  - Integrated `resvg-py` (Rust-based standalone SVG engine) for generating OpenGraph PNG cards identical to browser SVG rendering.
  - Eliminated bitmap font degradation and missing glyphs on Linux/Docker environments.
- **Emoji Visual Badge Alignment**:
  - Enlarged emoji font size to 32px and spaced them evenly across the full width of the identicon box (`x=80` to `x=280`).

---

## [1.5.0] - 2026-08-21

### Added
- **Anti-Impersonation Visual Key Verification**:
  - Implemented 5x5 horizontally symmetric Unicode block identicons (`██`) for instant visual key recognition.
  - Implemented a deterministic 5-emoji visual badge system providing ~40 bits of visual entropy from a 256-emoji curated dictionary.
  - Formatted PGP key fingerprints into standard Delta Chat client 10-group layout (2 lines of 5 groups of 4 uppercase hex characters).
  - Added registration age calculation (e.g. `19 Aug 2026 (2 days ago)`) to distinguish established accounts from fresh squatters.
  - Enhanced `/username` and `/username <target>` command responses with rich verification cards.
- **Smart Crawler Detection & OpenGraph Link Previews**:
  - Implemented User-Agent crawler detection for Telegram, Discord, Twitter, WhatsApp, Facebook, Matrix, iMessage, etc.
  - Crawlers receive full `og:title`, `og:description`, and `og:image` metadata with direct `<meta http-equiv="refresh">` fallback instead of generic empty fragment pages.
  - Regular browser visitors continue to receive instant `HTTP 307 Temporary Redirect` directly to Delta Chat invite links.
- **Dynamic OpenGraph Images, Avatars, & Web Cards**:
  - `GET /{username}/og.png`: Generates crisp 1200x630 OpenGraph cards using Pillow with fast in-memory LRU caching and HTTP cache headers.
  - `GET /{username}/og.svg` & `GET /{username}/avatar.svg`: Generates scalable vector avatars with deterministic colors based on key fingerprints.
  - `GET /{username}/card`: Dedicated web verification page with QR code, formatted fingerprint, email, identicon, and one-click chat launcher.
  - Automatic cache invalidation when usernames are claimed, modified, or unlinked.

---

## [1.4.4] - 2026-07-26

### Fixed
- **Admin Multi-Username Support (`/link`)**:
  - Fixed an issue where an administrator adding additional usernames in private chat (e.g. `/link stickers <channel_url>`) unintentionally overwrote and unlinked the admin's personal profile username (`gluek`).
  - Admins can now register an unlimited number of custom username links without affecting their personal primary username.

---

## [1.4.3] - 2026-07-26

### Fixed
- **Support Channel & Broadcast Invite Links**:
  - Expanded `validate_invite_link` in `bot.py` to support Delta Chat channel and broadcast invite URLs.
  - Channel/broadcast links use token parameters `x` and `j` (instead of standard contact token `i`) and broadcast parameter `b`.

---

## [1.4.2] - 2026-07-26

### Changed
- **Updated Icon & Favicon**:
  - Generated new `icon.png` and multi-resolution `favicon.ico` (16x16, 32x32, 48x48, 64x64) from `icon.jpg`.

---

## [1.4.1] - 2026-07-26

### Fixed
- **Proxy Headers Trust (`proxy_headers=True`)**:
  - Configured Uvicorn server in `bot.py` with `proxy_headers=True` and `forwarded_allow_ips="*"`.
  - Enables Uvicorn to parse `X-Forwarded-For` from reverse proxies (such as Caddy inside Docker) and print real client IP addresses in logs and rate limit checks.

---

## [1.4.0] - 2026-07-26

### Added
- **Built-in Application-Level Rate Limiting**:
  - Implemented an IP-based sliding window rate limiter on the `GET /{username}` redirect route.
  - Limits requests to 10 per minute per IP address to prevent automated username enumeration attacks.
  - Returns `HTTP 429 Too Many Requests` with a `Retry-After: 60` header and user-friendly error page upon limit breach.
  - Configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` environment variables.

---

## [1.3.2] - 2026-07-26

### Fixed
- **Dynamic HTTP 307 Redirect Domain Rewriting (`GET /{username}`)**:
  - Ensured `redirect_username` dynamically calls `rewrite_invite_link` on stored database links.
  - Changing `/inviteurl` or `INVITE_BASE_URL` now instantly applies to all existing and new short URLs without requiring users to re-link their usernames.

---

## [1.3.1] - 2026-07-26

### Changed
- **Direct Delta Chat Invite Link Lookup (`/username <name>`)**:
  - `/username <name>` now returns the direct canonical `https://i.delta.chat/#...` invite link instead of the short redirect link.
  - This allows the Delta Chat application to natively recognize the link in chat, highlight it, and open the target contact/group directly without opening an external browser.

---

## [1.3.0] - 2026-07-26

### Added
- **Configurable Custom Invite Domain (`INVITE_BASE_URL`)**:
  - Added support for custom invite domains/mirrors (e.g. `https://i.gluek.info/#`) to bypass DPI blocks on `i.delta.chat`.
  - Configurable via environment variable `INVITE_BASE_URL` or admin command `/inviteurl <url>`.
  - Automatically rewrites generated group chat and bot QR code invite links to use the mirror domain.
  - Link validation accepts any mirror domain with valid Delta Chat parameters.

---

## [1.2.0] - 2026-07-26

### Added
- **Public Username Lookup (`/username <name>`)**: Any user can now look up the short link for any registered username via `/username <name>`.
- **Single-Step Explicit Linking (`/link`)**:
  - Private chats: `/link <username> <invite_link>` binds a custom username and invite URL in a single step.
  - Group chats: `/link <username>` automatically generates the group invite link via RPC and binds it.
  - Previous username replacement: If a chat already had a username, claiming a new one automatically unlinks the previous username and notifies the user.
- **Admin Custom Linking**: Admins can force-link any username to any invite link.

### Removed
- **Passive Link Watching**: Removed passive listening and error comments on standard text messages containing `i.delta.chat` links in `on_new_message`.

---

## [1.1.0] - 2026-07-25

### Added
- **`/unlink` Command**: Users and group chats can now unlink their active username without parameters (`/unlink`). Administrators can force-unlink any username (`/unlink <username>`).
- **`/link` Admin Command**: Administrators can manually bind or create any username link to an invite URL (`/link <username> <invite_link>`).

### Changed
- **Minimum Username Length**: Lowered minimum username length requirement from 5 to 3 characters for all users.
- **One Username Per Chat Restriction**: Enforced a strict maximum of 1 active username per chat/group. Claiming a new username automatically replaces and unlinks the previous one.
- **Improved Group Chat Detection & Invite Links**: Robust multi-fallback group chat detection (`get_basic_chat_info` -> `get_full_chat_by_id` -> `get_chat_contacts`) and RPC invite link extraction via `get_chat_securejoin_qr_code`.
- **Favicon & Avatar**: Added `favicon.ico` auto-generation and route serving via FastAPI.

---

## [1.0.0] - 2026-07-24

### Added
- Initial release of **Delta Chat Username Bot (`deltachat_username`)**.
- Username reservation logic for individual users and group chats via `/username`.
- Automatic group invite URL fetching for group chat username claims.
- FastAPI backend service providing HTTP 307 Temporary Redirect for registered short URLs (`GET /{username}`).
- Modern dark glassmorphism landing page (`GET /`) displaying bot description, QR code, and command hints.
- SQLite storage layer for persistent claim mappings, pending reservation states, and transport statistics.
- Secure administrative setup via `/initadmin` and CLI script `set_admin.py`.
- Auto-update script `update.sh` with Healthchecks monitoring and Forgejo fallback support.
- Docker & Docker Compose setup, Caddy reverse proxy template, unit tests, and GitHub Actions CI workflow.
