# Changelog

All notable changes to the **Delta Chat Username Bot (`deltachat_username`)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
