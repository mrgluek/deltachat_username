# Changelog

All notable changes to the **Delta Chat Username Bot (`deltachat_username`)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
