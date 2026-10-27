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
- 🔄 **Contact Sync**: A personal link follows its owner. When they write to the bot in the private chat where the link was registered, and once an hour for all personal links, the bot updates `a=` (address), `r=` (further relays, from the relay list in the contact's key) and `n=` (name). Relay changes reach the bot through the core's keyupdate messages (core 2.60+) even if the owner never writes. Only links with the contact's own key fingerprint are touched; fingerprint and invite tokens stay as they are, so a new key needs a new `/link`. Group, channel and ArcaneChat links are never rewritten.
- 🛡️ **Secure Administration**: Authenticate ownership via `/initadmin` with cryptographic fingerprint verification.
- 🔮 **ArcaneChat Admin Groups**: Invite links of ArcaneChat admin groups (`z=` parameter) are supported and shown as groups, marked **ArcaneChat only** in the chat card, `/link` reply, web page (no auto-redirect; the "Open in ArcaneChat" button is an `openpgp4fpr:` link that opens the installed app directly), social preview cards and the API (`"arcanechat_only": true`). They open only in [ArcaneChat](https://arcanechat.me); Delta Chat would open a 1:1 chat with the inviter. The link is never rewritten when its owner writes to the bot.
- 🤝 **Lookup API for Bots** (`GET /api/username/<name>`): returns `{username, type, arcanechat_only, display_name, url, invite_link}` as JSON, or 404 `{"error": "not_found"}`. `url` is the short link, `invite_link` the invite on `i.delta.chat` (the same link `/username` sends), which Delta Chat apps open directly without a browser. Bouncer Bot uses it to point people to a mentioned user who is not in the group. Shares the 10 requests/minute per IP limit with profile pages (429 `{"error": "rate_limited"}`).
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

### 2. Configure Email and Admin (Optional)

Skip this step and the bot creates its account by itself at first start: the Delta Chat core (2.62+) picks the fastest chatmail relay from its built-in list and later adds further relays in the background.

To choose the account yourself, initialize it with your email and password, or with `DCACCOUNT:server.tld` for an account on a specific chatmail relay:

```bash
docker compose run --rm username_bot python bot.py init usernamebot@yourdomain.com "your_password"
docker compose run --rm username_bot python bot.py init DCACCOUNT:server.tld
```

Configure your admin email address and your cryptographic fingerprint on the server (or do it later inside the bot chat with the `/initadmin` command):

```bash
docker compose run --rm username_bot python set_admin.py --email admin@yourdomain.com
docker compose run --rm username_bot python set_admin.py --fingerprint 1234ABCD1234ABCD1234ABCD1234ABCD1234ABCD
```

### 3. Launch Bot Daemon

```bash
docker compose up -d
```

### 4. Claim Administrative Ownership

Send `/initadmin` to the bot in a private message in Delta Chat to complete admin identity verification.

### 5. Updates

Run `./update.sh` (e.g. from cron) to deploy the newest release: the highest `vX.Y.Z` tag, from GitHub or, when GitHub is unreachable, from the Forgejo mirror; `-f` rebuilds the container without changes. Commits on `main` that are not released yet are not deployed. In `.env.local`, `UPDATE_REF=v1.13.0` stays on that release (to roll back; remove it to follow new releases again), `UPDATE_REF=main` follows the branch, and `MONITOR_URL` pings a healthcheck on start, success and failure.

Releasing: merge, then `git tag -a vX.Y.Z -m "..." <commit> && git push origin vX.Y.Z`. Pushing the tag publishes the GitHub release with that version's `CHANGELOG.md` section (the tag must match `VERSION` in `commands.py`), then sends the ntfy notification and the Home Assistant add-on sync.

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

## License

MIT, see [LICENSE](LICENSE).
