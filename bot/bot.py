"""
Bot Entry Point
===============
Wires up the Telegram Application, registers handlers, and runs polling.
"""

from __future__ import annotations

from telegram import Update
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


async def _post_init(app: Application) -> None:
    handlers: BotHandlers = app.bot_data["handlers"]
    handlers.set_bot_app(app)
    await handlers.on_startup()
    logger.info("Bot is ready and polling.")


async def _post_shutdown(app: Application) -> None:
    handlers: BotHandlers = app.bot_data["handlers"]
    await handlers.on_shutdown()
    logger.info("Bot shut down cleanly.")


def run_bot() -> None:
    cfg = get_settings()
    token = cfg.telegram.token

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise ValueError(
            "Telegram bot token not set.\n"
            "Edit config/config.yaml → telegram.token and set your token.\n"
            "Get a token from @BotFather on Telegram."
        )

    handlers = BotHandlers()

    # ── HTTP client مع مهلات مرتفعة لدعم رفع الملفات الكبيرة ──────────────
    # read_timeout / write_timeout مرتفعان لاستيعاب رفع ملفات ZIP تصل
    # إلى 40 MB دون انقطاع الاتصال (httpx.ReadError / TimedOut).
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=60,
        read_timeout=600,   # 10 دقائق — كافية لأكبر أجزاء التصدير
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

    # ── commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    
    # ── أوامر الإدارة ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin", handlers.cmd_admin))
    app.add_handler(CommandHandler("broadcast", handlers.cmd_broadcast))
    app.add_handler(CommandHandler("stats", handlers.cmd_stats))
    app.add_handler(CommandHandler("export", handlers.cmd_export))
    app.add_handler(CommandHandler("rebuild", handlers.cmd_rebuild))

    # تسجيل معالج الأزرار الشفافة الخاصة بلوحة التحكم
    app.add_handler(CallbackQueryHandler(handlers.handle_admin_callbacks, pattern="^admin_"))

    # ── text messages (معالج الأزرار السفلية) ──────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))

    # ── audio messages ────────────────────────────────────────────────────
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

    logger.info("Starting Telegram bot (polling mode)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
