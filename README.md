# 🔗 Delta Chat Username & Short Link Bot (`deltachat_username`)

A Delta Chat bot and FastAPI web service for registering custom usernames and generating short invite links (`https://deltachat.id/<username>`) that redirect (via HTTP 307 Temporary Redirect) to standard Delta Chat invite URLs (`https://i.delta.chat/#...`).

---

## ✨ Features

- 👤 **Custom Usernames**: Claim a short username (`/username myname`) for your personal profile or group chat.
- 🔐 **Visual Cryptographic Verification**: Anti-impersonation verification displaying 10-group formatted PGP fingerprints, 5x5 symmetric Unicode block Identicons, and 5-emoji visual badges.
- 🖼️ **Social OpenGraph & Twitter Cards**: Smart crawler detection serving rich metadata and cached dynamic PNG cards (`1200x630`) on Telegram, Discord, Twitter, WhatsApp, etc.
- 📇 **Web Profile Cards & Avatars**: Dynamic endpoints (`/{username}/og.png`, `/{username}/avatar.svg`, and `/{username}/card`) for visual badges, QR codes, and web verification.
- ⚡️ **Group Chat Auto-Binding**: Use `/username myname` directly inside any group chat — the bot instantly generates the group's invite URL without manual link pasting.
- 🔀 **HTTP 307 Temporary Redirect**: Guarantees browsers and proxies always fetch the newest invite link without aggressive caching.
- 🌐 **Web Landing Page**: Beautiful dark-mode glassmorphism interface on `GET /` displaying bot description, QR code, and interactive command hints.
- 🛡️ **Secure Administration**: Authenticate ownership via `/initadmin` with cryptographic fingerprint verification.
- 🤝 **Lookup API for Bots** (`GET /api/username/<name>`): returns `{username, type, display_name, url, invite_link}` as JSON, or 404 `{"error": "not_found"}`. `url` is the short link, `invite_link` the invite on `i.delta.chat` (the same link `/username` sends), which Delta Chat apps open directly without a browser. Bouncer Bot uses it to point people to a mentioned user who is not in the group. Shares the 10 requests/minute per IP limit with profile pages (429 `{"error": "rate_limited"}`).
- 📡 **Multi-Transport**: Configure backup transports and see which relay the core sends through (`/transports`).

---

## 🚀 Quick Start & Deployment

### 1. Build Container

Clone repository and navigate to `deltachat_username`:

```bash
cd deltachat_username
cp .env.example .env
docker compose build
```

### 2. Initialize Delta Chat Account

Initialize the bot's account in Delta Chat CLI (`deltabot-cli`):

```bash
# Option A: Automatic setup on a Chatmail server (e.g. chatmail.uk or nine.testrun.org)
docker compose run --rm username_bot python bot.py init usernamebot@chatmail.uk

# Option B: Standard email account with password
docker compose run --rm username_bot python bot.py init usernamebot@yourdomain.com "your_password"
```

### 3. (Optional) Pre-configure Admin Email / Fingerprint

```bash
docker compose run --rm username_bot python set_admin.py --email admin@yourdomain.com
```

### 4. Launch Bot Daemon

```bash
docker compose up -d
```

### 5. Claim Administrative Ownership

Send `/initadmin` to the bot in a private message in Delta Chat to complete admin identity verification.

---

## 🤖 Bot Commands

| Command | Scope | Description |
|---|---|---|
| `/username` | All | Check your current chat's registered username and short link. |
| `/username <name>` | All | Look up short link for any registered username. |
| `/link <name> <url>` | Private | Bind custom username & invite link (replaces old username if present). |
| `/link <name>` | Group | Auto-generate group invite link and bind username. |
| `/unlink` | All | Unlink registered username from current chat. |
| `/unlink <name>` | Admin | Force-unlink a registered username. |
| `/help` | All | Show command help and bot info. |
| `/donate` | All | Support bot development. |
| `/initadmin` | Admin | Claim administrative ownership. |
| `/url <url>` | Admin | Set base domain URL (`https://deltachat.id`). |
| `/inviteurl <url>` | Admin | Set custom invite base URL/mirror (`https://i.gluek.info/#`). |
| `/stats` | Admin | Show registered usernames and database stats. |
| `/transports` | Admin | Show mail relays: relay used for sending, send queue, incoming status and storage. |
| `/addtransport <uri/creds>` | Admin (Private) | Add a backup mail transport relay. |
| `/rmtransport <addr>` | Admin | Remove a configured mail transport. |

Relay selection and failover are handled by the Delta Chat core (2.61+): it keeps sending through the relay that last worked and moves to the next one only if it cannot connect, so the relay used for sending can differ from the account's main address. `/transports` shows which relay that is, the core's send queue, and per relay the incoming status, the last received message and mailbox storage. The former `/setprimary` and `/resilient` commands are deprecated and only reply with this explanation.

---

### Target-Specific Commands in Group Chats

In group chats where multiple bots are present, you can address this bot specifically to prevent other bots from responding. Append the `@username` (or `@user`, `@usernamebot`) suffix to any command, for example:
- `/help@username`
- `/stats@username`

A plain `/help` sent in a group chat is answered in a private 1:1 chat with the sender, so several bots don't flood the group with help texts. Use `/help@username` to show the help in the group itself.

## 🌐 Caddy Configuration

Add to your `/etc/caddy/Caddyfile`:

```caddy
deltachat.id, d.gluek.info {
    reverse_proxy 127.0.0.1:8080
}

www.deltachat.id {
    redir https://deltachat.id{uri} permanent
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

- ⭐ **Star** this repository or bookmark it!
  - **Git Repository:** [mrgluek/deltachat_username](https://github.com/mrgluek/deltachat_username)
  - **Forgejo Mirror:** [gluek/deltachat_username](https://git.gluek.info/gluek/deltachat_username)
- **Donations:**
  - ☕️ [Ko-fi](https://ko-fi.com/gluek) (world cards, PayPal)
  - 🚀 [Tribute](https://web.tribute.tg/d/IWb) (Russian cards, SBP)
  - Or use the `/donate` command in Delta Chat.
