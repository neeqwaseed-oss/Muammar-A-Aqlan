"""
Bot Entry Point  (v3)
=====================
Wires up the Telegram Application, registers handlers, and runs polling.

Conflict fix
------------
Error 409 Conflict means another instance is already polling.
We register an error handler that catches telegram.error.Conflict,
logs a clear message, and shuts the bot down cleanly so only one
instance runs at a time.
"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config.settings import get_settings
from bot.handlers import BotHandlers
from utils.logger import get_logger

logger = get_logger(__name__)


# ── lifecycle hooks ────────────────────────────────────────────────────────

async def _post_init(app: Application) -> None:
    handlers: BotHandlers = app.bot_data["handlers"]
    handlers.set_bot_app(app)
    await handlers.on_startup()
    logger.info("✅ Bot is ready and polling.")


async def _post_shutdown(app: Application) -> None:
    handlers: BotHandlers = app.bot_data["handlers"]
    await handlers.on_shutdown()
    logger.info("🛑 Bot shut down cleanly.")


# ── global error handler ───────────────────────────────────────────────────

async def _error_handler(update: object, context) -> None:
    exc = context.error

    if isinstance(exc, Conflict):
        # 409: another instance is running — shut this one down immediately
        logger.critical(
            "⚠️  Conflict (409): another bot instance is already running.\n"
            "   Stop all other instances and restart.  This instance will exit."
        )
        # Signal the application to stop
        asyncio.create_task(context.application.stop())
        return

    # All other errors: log and continue
    logger.exception(
        "Unhandled exception for update %s",
        update,
        exc_info=exc,
    )


# ── main entry point ───────────────────────────────────────────────────────

def run_bot() -> None:
    cfg   = get_settings()
    token = cfg.telegram.token

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise ValueError(
            "Telegram bot token not set.\n"
            "Edit config/config.yaml → telegram.token\n"
            "Get a token from @BotFather on Telegram."
        )

    handlers = BotHandlers()

    # ── HTTP client with high timeouts for large file uploads ─────────────
    # read/write_timeout=600 handles ZIP uploads up to 40 MB without
    # dropping the connection (httpx.ReadError / TimedOut).
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=60,
        read_timeout=600,    # 10 min — enough for the largest export parts
        write_timeout=600,
        pool_timeout=60,
    )

    app = (
        Application.builder()
        .token(token)
        .request(request)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["handlers"] = handlers

    # Register the global error handler (catches Conflict + all others)
    app.add_error_handler(_error_handler)

    # ── commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     handlers.cmd_start))
    app.add_handler(CommandHandler("help",      handlers.cmd_help))
    app.add_handler(CommandHandler("admin",     handlers.cmd_admin))
    app.add_handler(CommandHandler("broadcast", handlers.cmd_broadcast))
    app.add_handler(CommandHandler("stats",     handlers.cmd_stats))
    app.add_handler(CommandHandler("export",    handlers.cmd_export))
    app.add_handler(CommandHandler("rebuild",   handlers.cmd_rebuild))

    # ── inline keyboard callbacks ─────────────────────────────────────────
    app.add_handler(
        CallbackQueryHandler(handlers.handle_admin_callbacks, pattern="^admin_")
    )

    # ── text (reply keyboard buttons) ─────────────────────────────────────
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text)
    )

    # ── audio / voice / document ──────────────────────────────────────────
    audio_filter = (
        filters.VOICE
        | filters.AUDIO
        | filters.Document.AUDIO
        | filters.Document.FileExtension("ogg")
        | filters.Document.FileExtension("oga")
        | filters.Document.FileExtension("mp3")
        | filters.Document.FileExtension("wav")
        | filters.Document.FileExtension("m4a")
        | filters.Document.FileExtension("flac")
    )
    app.add_handler(MessageHandler(audio_filter, handlers.handle_audio))

    logger.info("🚀 Starting Telegram bot (polling mode)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
