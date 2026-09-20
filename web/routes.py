import os

from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

import database
import identicon
from security import get_client_ip, is_rate_limited
from formatting import BASE_URL, get_request_base_url, rewrite_invite_link, generate_qr_data_uri

app = FastAPI(title="Delta Chat Username Service")


@app.get("/favicon.ico")
def get_favicon():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fav_path = os.path.join(base_dir, "favicon.ico")
    if os.path.exists(fav_path):
        return FileResponse(fav_path, media_type="image/x-icon")
    icon_path = os.path.join(base_dir, "icon.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    return Response(status_code=404)


@app.get("/", response_class=HTMLResponse)
def get_index_page(request: Request):
    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        return HTMLResponse(
            content="""<!DOCTYPE html><html><head><title>429 Too Many Requests</title></head><body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;text-align:center;padding:50px;"><h1>429 - Too Many Requests</h1><p>Please wait a minute before trying again.</p></body></html>""",
            status_code=429,
            headers={"Retry-After": "60"}
        )

    base_url = database.get_config("base_url") or BASE_URL
    bot_invite = database.get_config("bot_invite_url") or ""
    bot_addr = database.get_config("bot_addr") or ""

    qr_img = generate_qr_data_uri(bot_invite) if bot_invite else ""

    qr_html = ""
    if qr_img:
        qr_html = f'''
        <div class="qr-container">
            <img src="{qr_img}" alt="Delta Chat Bot QR Code" class="qr-code">
            <a href="{bot_invite}" class="btn-primary">💬 Start Chat in Delta Chat</a>
        </div>
        '''
    elif bot_invite:
        qr_html = f'''
        <div class="qr-container">
            <a href="{bot_invite}" class="btn-primary">💬 Start Chat in Delta Chat</a>
        </div>
        '''
    elif bot_addr:
        qr_html = f'''
        <div class="qr-container">
            <p>Send an email/message in Delta Chat to: <code>{bot_addr}</code></p>
        </div>
        '''

    total_usernames = database.get_username_count()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delta Chat Username & Short Link Service</title>
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-color: #38bdf8;
            --accent-hover: #0284c7;
            --code-bg: #020617;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            width: 100%;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        header {{ text-align: center; margin-bottom: 30px; }}
        h1 {{ font-size: 2rem; margin-bottom: 10px; color: var(--text-primary); }}
        p.subtitle {{ color: var(--text-secondary); font-size: 1.1rem; }}
        .badge {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-color);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.875rem;
            margin-top: 10px;
        }}
        .qr-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 25px 0;
            padding: 20px;
            background: rgba(15, 23, 42, 0.4);
            border-radius: 16px;
            border: 1px solid var(--border-color);
        }}
        .qr-code {{
            width: 180px;
            height: 180px;
            border-radius: 12px;
            margin-bottom: 15px;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3);
        }}
        .btn-primary {{
            display: inline-block;
            background: var(--accent-color);
            color: #0f172a;
            font-weight: 600;
            padding: 12px 24px;
            border-radius: 12px;
            text-decoration: none;
            transition: all 0.2s ease;
        }}
        .btn-primary:hover {{
            background: var(--accent-hover);
            color: #ffffff;
            transform: translateY(-2px);
        }}
        .section-title {{
            font-size: 1.25rem;
            margin: 30px 0 15px 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }}
        .commands-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
        }}
        .command-card {{
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
        }}
        .command-name {{
            font-family: monospace;
            font-size: 1rem;
            color: var(--accent-color);
            margin-bottom: 4px;
        }}
        .command-desc {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}
        footer {{
            text-align: center;
            margin-top: 35px;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}
        footer a {{ color: var(--accent-color); text-decoration: none; }}
        code {{
            background: var(--code-bg);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            color: #e2e8f0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔗 Delta Chat Username Service</h1>
            <p class="subtitle">Short custom invite links for Delta Chat users and group chats</p>
            <span class="badge">Active Registered Usernames: {total_usernames}</span>
        </header>

        {qr_html}

        <h2 class="section-title">⚡️ How It Works</h2>
        <div class="commands-grid">
            <div class="command-card">
                <div class="command-name">/username [name]</div>
                <div class="command-desc">View your registered username, or look up direct Delta Chat invite link for any username.</div>
            </div>
            <div class="command-card">
                <div class="command-name">/link myname [link]</div>
                <div class="command-desc">Claim or update custom username (min 3 characters).
                <br>• <strong>Private Chat:</strong> Send <code>/link myname https://i.delta.chat/#...</code>
                <br>• <strong>Group Chat:</strong> Send <code>/link myname</code> to auto-generate group invite link.
                </div>
            </div>
            <div class="command-card">
                <div class="command-name">/unlink</div>
                <div class="command-desc">Unlink the current registered username from this chat.</div>
            </div>
        </div>

        <footer>
            Powered by <a href="https://github.com/mrgluek/deltachat_username" target="_blank">Delta Chat Username Bot</a> (<a href="https://git.gluek.info/gluek/deltachat_username" target="_blank">Mirror</a>)
        </footer>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/health")
def health_check():
    return {"status": "ok", "usernames_claimed": database.get_username_count()}


@app.get("/{username}")
@app.get("/{username}/")
def redirect_username(username: str, request: Request):
    clean_username = username.strip("/").strip().lower()

    # Rate Limit Check (10 requests per minute per IP)
    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>429 - Too Many Requests</title>
    <style>
        body {
            background: #0f172a; color: #f8fafc;
            font-family: system-ui, sans-serif;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; margin: 0; text-align: center;
        }
        .card {
            background: rgba(30, 41, 59, 0.8); padding: 40px; border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1); max-width: 450px;
        }
        h1 { font-size: 3rem; margin-bottom: 10px; color: #f59e0b; }
        p { color: #94a3b8; font-size: 1.1rem; margin-bottom: 20px; }
        a { color: #38bdf8; text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>
    <div class="card">
        <h1>429</h1>
        <p>Too many requests. Please wait a minute before trying again.</p>
        <a href="/">Go to Homepage</a>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html, status_code=429, headers={"Retry-After": "60"})

    claim = database.get_username_claim(clean_username)

    if claim and claim.get("invite_link"):
        target_link = rewrite_invite_link(claim["invite_link"])
        base_url = get_request_base_url(request)
        metadata = identicon.parse_invite_metadata(claim["invite_link"], claim.get("updated_at", ""))

        title_name = metadata.get("display_name") or clean_username
        og_title = f"{title_name} (@{clean_username}) • Delta Chat"
        fp_l1, fp_l2 = metadata.get("formatted_fp", ("", ""))
        if metadata.get("target_type") == "group":
            target_desc = f"👥 Group: {metadata.get('display_name')}"
        elif metadata.get("target_type") == "channel":
            target_desc = f"📢 Channel: {metadata.get('display_name')}"
        else:
            target_desc = f"📧 {metadata.get('email') or 'Delta Chat User'}"

        og_desc = (
            f"{target_desc} • "
            f"🔐 FP: {fp_l1} • "
            f"🛡️ {metadata.get('emoji_hash')} • "
            f"📅 Linked: {metadata.get('relative_time')}"
        )
        og_img = f"{base_url}/{clean_username}/og.png"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{og_title}</title>
    <!-- OpenGraph / Facebook / Telegram / Discord / WebPreview -->
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Delta Chat Username Service">
    <meta property="og:title" content="{og_title}">
    <meta property="og:description" content="{og_desc}">
    <meta property="og:image" content="{og_img}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:type" content="image/png">
    <meta property="og:url" content="{base_url}/{clean_username}">
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{og_title}">
    <meta name="twitter:description" content="{og_desc}">
    <meta name="twitter:image" content="{og_img}">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <script>
        if (!window.location.search.includes("preview=1")) {{
            window.location.replace("{target_link}");
        }}
    </script>
    <style>
        body {{
            background: #0f172a; color: #f8fafc;
            font-family: system-ui, sans-serif;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; margin: 0; padding: 20px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,0.1); border-radius: 24px;
            padding: 35px; max-width: 500px; width: 100%; text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }}
        h1 {{ font-size: 1.8rem; margin-bottom: 6px; }}
        p.sub {{ color: #38bdf8; font-weight: 600; margin-bottom: 20px; }}
        .fp {{ font-family: monospace; background: #020617; padding: 12px; border-radius: 10px; font-size: 0.9rem; color: #38bdf8; margin: 15px 0; word-break: break-all; }}
        .btn {{ display: inline-block; background: #38bdf8; color: #0f172a; padding: 12px 24px; border-radius: 12px; text-decoration: none; font-weight: bold; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{title_name}</h1>
        <p class="sub">@{clean_username}</p>
        <p>Linked {metadata.get('relative_time')}</p>
        <div class="fp">{fp_l1}<br>{fp_l2}</div>
        <p style="font-size: 1.5rem; margin: 10px 0;">{metadata.get('emoji_hash')}</p>
        <a href="{target_link}" class="btn">💬 Open in Delta Chat</a>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html, status_code=200)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>404 - Username Not Found</title>
    <style>
        body {{
            background: #0f172a; color: #f8fafc;
            font-family: system-ui, sans-serif;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; margin: 0; text-align: center;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.8); padding: 40px; border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1); max-width: 450px;
        }}
        h1 {{ font-size: 3rem; margin-bottom: 10px; color: #ef4444; }}
        p {{ color: #94a3b8; font-size: 1.1rem; margin-bottom: 20px; }}
        a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>404</h1>
        <p>The username <code>{clean_username}</code> is not registered or has no active invite link.</p>
        <a href="/">Go to Homepage</a>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=404)


@app.get("/{username}/og.png")
def get_username_og_png(username: str, request: Request):
    clean_username = username.strip().lower()
    claim = database.get_username_claim(clean_username)
    if not claim or not claim.get("invite_link"):
        return Response(status_code=404)

    base_url = get_request_base_url(request)
    metadata = identicon.parse_invite_metadata(claim["invite_link"], claim.get("updated_at", ""))
    png_bytes = identicon.generate_og_png_bytes(clean_username, metadata, base_url=base_url)
    if not png_bytes:
        return Response(status_code=500)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=3600"},
    )


@app.get("/{username}/og.svg")
@app.get("/{username}/avatar.svg")
def get_username_avatar_svg(username: str, request: Request):
    clean_username = username.strip().lower()
    claim = database.get_username_claim(clean_username)
    if not claim or not claim.get("invite_link"):
        return Response(status_code=404)

    base_url = get_request_base_url(request)
    metadata = identicon.parse_invite_metadata(claim["invite_link"], claim.get("updated_at", ""))
    svg_text = identicon.generate_svg_card(clean_username, metadata, base_url=base_url)

    return Response(
        content=svg_text,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=3600"},
    )


@app.get("/{username}/card", response_class=HTMLResponse)
def get_username_card_page(username: str, request: Request):
    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        return HTMLResponse(
            content="""<!DOCTYPE html><html><head><title>429 Too Many Requests</title></head><body style="background:#0f172a;color:#f8fafc;font-family:sans-serif;text-align:center;padding:50px;"><h1>429 - Too Many Requests</h1><p>Please wait a minute before trying again.</p></body></html>""",
            status_code=429,
            headers={"Retry-After": "60"}
        )

    clean_username = username.strip().lower()
    claim = database.get_username_claim(clean_username)
    if not claim or not claim.get("invite_link"):
        return Response(status_code=404)

    base_url = get_request_base_url(request)
    target_link = rewrite_invite_link(claim["invite_link"])
    metadata = identicon.parse_invite_metadata(claim["invite_link"], claim.get("updated_at", ""))
    qr_img = generate_qr_data_uri(target_link)

    title_name = metadata.get("display_name") or clean_username
    line1, line2 = metadata.get("formatted_fp", ("", ""))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_name} (@{clean_username}) • Delta Chat</title>
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <meta property="og:title" content="{title_name} (@{clean_username}) • Delta Chat">
    <meta property="og:image" content="{base_url}/{clean_username}/og.png">
    <style>
        body {{
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            min-height: 100vh; display: flex; justify-content: center; align-items: center;
            padding: 20px; box-sizing: border-box;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.75); backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 24px;
            padding: 40px; max-width: 540px; width: 100%; text-align: center;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        .avatar {{ width: 120px; height: 120px; border-radius: 20px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.1); }}
        h1 {{ font-size: 2rem; margin-bottom: 4px; }}
        .username {{ color: #38bdf8; font-size: 1.2rem; font-weight: 600; margin-bottom: 15px; }}
        .badge {{ display: inline-block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 4px 14px; border-radius: 999px; font-size: 0.875rem; margin-bottom: 20px; }}
        .info-box {{ background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; margin: 15px 0; text-align: left; }}
        .info-label {{ font-size: 0.8rem; font-weight: bold; color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; }}
        .fp-text {{ font-family: monospace; font-size: 0.95rem; color: #38bdf8; letter-spacing: 1px; word-break: break-all; }}
        .qr-box {{ margin: 20px 0; }}
        .qr-code {{ width: 160px; height: 160px; border-radius: 12px; }}
        .btn {{ display: block; background: #38bdf8; color: #0f172a; padding: 14px 20px; border-radius: 12px; font-weight: 600; text-decoration: none; font-size: 1.05rem; transition: 0.2s; }}
        .btn:hover {{ background: #0284c7; color: white; }}
    </style>
</head>
<body>
    <div class="card">
        <img src="/{clean_username}/og.svg" alt="Identicon" class="avatar">
        <h1>{title_name}</h1>
        <div class="username">@{clean_username}</div>
        <span class="badge">Linked: {metadata.get('relative_time')}</span>

        <div class="info-box">
            <div class="info-label">Email</div>
            <div><code>{metadata.get('email') or 'Not specified'}</code></div>
        </div>

        <div class="info-box">
            <div class="info-label">Cryptographic Fingerprint</div>
            <div class="fp-text">{line1}<br>{line2}</div>
        </div>

        <div class="info-box" style="text-align: center;">
            <div class="info-label">Visual Key Badge</div>
            <div style="font-size: 1.6rem; margin-top: 4px;">{metadata.get('emoji_hash')}</div>
        </div>

        {f'<div class="qr-box"><img src="{qr_img}" class="qr-code"></div>' if qr_img else ''}

        <a href="{target_link}" class="btn">💬 Start Chat in Delta Chat</a>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)
