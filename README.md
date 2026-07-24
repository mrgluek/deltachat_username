# 🔗 Delta Chat Username & Short Link Bot (`deltachat_username`)

A Delta Chat bot and FastAPI web service for registering custom usernames and generating short invite links (`https://d.gluek.info/<username>`) that redirect (via HTTP 307 Temporary Redirect) to standard Delta Chat invite URLs (`https://i.delta.chat/#...`).

---

## ✨ Features

- 👤 **Custom Usernames**: Claim a short username (`/username myname`) for your personal profile or group chat.
- ⚡️ **Group Chat Auto-Binding**: Use `/username myname` directly inside any group chat — the bot instantly generates the group's invite URL without manual link pasting.
- 🔀 **HTTP 307 Temporary Redirect**: Guarantees browsers and proxies always fetch the newest invite link without aggressive caching.
- 🌐 **Web Landing Page**: Beautiful dark-mode glassmorphism interface on `GET /` displaying bot description, QR code, and interactive command hints.
- 🛡️ **Secure Administration**: Authenticate ownership via `/initadmin` with cryptographic fingerprint verification.
- 📡 **Multi-Transport & Statistics**: Track sent/received relay stats and configure backup transports.

---

## 🚀 Quick Start

### Docker Compose (Recommended)

1. Clone repository and navigate to `deltachat_username`:
   ```bash
   cd deltachat_username
   ```

2. Copy environment template:
   ```bash
   cp .env.example .env
   ```

3. Build and launch containers:
   ```bash
   docker compose up -d --build
   ```

4. Claim administrative ownership in private chat:
   ```text
   /initadmin
   ```

---

## 🤖 Bot Commands

| Command | Scope | Description |
|---|---|---|
| `/username` | All | Check current registered username and short link. |
| `/username <name>` | All | Claim or update a username (min 5 chars). |
| `/help` | All | Show command help and bot info. |
| `/donate` | All | Support bot development. |
| `/initadmin` | Admin | Claim administrative ownership. |
| `/url <url>` | Admin | Set base domain URL (`https://d.gluek.info`). |
| `/stats` | Admin | Show registered usernames and database stats. |
| `/transports` | Admin | List configured mail relays and statistics. |

---

## 🌐 Caddy Configuration

Add to your `/etc/caddy/Caddyfile`:

```caddy
d.gluek.info {
    reverse_proxy 127.0.0.1:8080
}
```

---

## 🧪 Running Unit Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## ❤️ Support & Development

If you find this bot useful, consider supporting its development:

- **Git Repository:** [mrgluek/deltachat_username](https://github.com/mrgluek/deltachat_username)
- **Forgejo Mirror:** [gluek/deltachat_username](https://git.gluek.info/gluek/deltachat_username)
- **Donations:**
  - ☕️ [Ko-fi](https://ko-fi.com/gluek) (world cards, PayPal)
  - 🚀 [Tribute](https://web.tribute.tg/d/IWb) (Russian cards, SBP)
  - Or use the `/donate` command in Delta Chat.
