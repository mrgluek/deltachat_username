# Changelog

All notable changes to the **Delta Chat Username Bot (`deltachat_username`)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
