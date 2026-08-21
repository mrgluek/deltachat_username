# Changelog

All notable changes to the **Delta Chat Username Bot (`deltachat_username`)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
