# إصلاحات الاستضافة — Render Deployment Fixes

## المشاكل التي تم حلها / Problems Fixed

### 1. خطأ 409 Conflict — Multiple Bot Instances

**السبب / Cause:**  
Render sets `WEB_CONCURRENCY=8` by default, spawning 8 worker processes. Each process tried to start the Telegram bot polling simultaneously, causing a `409 Conflict` error from Telegram's API.

**الإصلاح / Fix:**
- Added `ENV WEB_CONCURRENCY=1` to `Dockerfile`
- Added `render.yaml` that explicitly sets `WEB_CONCURRENCY=1`
- The existing PID lock in `main.py` now works correctly since only one process runs

---

### 2. No open ports detected

**السبب / Cause:**  
Render's **Web Service** type requires the app to bind to `$PORT` within ~60 seconds of startup. The bot never opened an HTTP port.

**الإصلاح / Fix:**  
Added `_start_health_server()` to `main.py`. It starts a tiny HTTP server (in a background daemon thread) on `$PORT` that returns `{"status":"ok"}` for any GET request. This satisfies Render's health check without interfering with the bot.

---

### 3. Token in public repository — Security Risk

**السبب / Cause:**  
`config/config.yaml` contained the real bot token and was committed to a public GitHub repository.

**الإصلاح / Fix:**  
- `config/settings.py` now reads `TELEGRAM_TOKEN` environment variable **first**, falling back to `config.yaml` only when the env var is not set.  
- `config/config.yaml` now contains the placeholder `YOUR_BOT_TOKEN_HERE`.
- `render.yaml` is configured to accept `TELEGRAM_TOKEN` as a secret env var set in the Render dashboard.

---

## خطوات النشر / Deployment Steps

1. **Copy these fixed files** to your GitHub repository (replace the originals).

2. **Revoke the old token** — your token was exposed in a public repo:
   - Go to [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/mybots` → select your bot → `API Token` → `Revoke current token`
   - Copy the new token

3. **Set the token in Render:**
   - Render dashboard → your service → **Environment**
   - Add: `TELEGRAM_TOKEN` = `<your new token>`

4. **Push to GitHub** and trigger a new deploy in Render.

5. **Stop any old running instances** before deploying to avoid 409 errors during the transition.

---

## ملخص الملفات المعدّلة / Changed Files

| File | Change |
|------|--------|
| `main.py` | Added `_start_health_server()` — HTTP health check on `$PORT` |
| `config/settings.py` | Reads `TELEGRAM_TOKEN` env var first |
| `config/config.yaml` | Replaced real token with placeholder |
| `Dockerfile` | Added `ENV WEB_CONCURRENCY=1` |
| `render.yaml` | **New file** — proper Render config with persistent disk |
| `.gitignore` | **New file** — excludes dataset, logs, temp directories |
