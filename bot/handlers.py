"""
Bot Handlers  (v3 — UI overhaul + concurrent multi-worker)
===========================================================
All Telegram command and message handlers live here.
All user-facing strings are imported from bot.ui so this file
stays clean and focused on logic only.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from telegram.error import TimedOut, NetworkError, RetryAfter

from config.settings import get_settings
from core.audio import AudioProcessor
from core.speech import Transcriber
from core.database import DatabaseManager
from core.dataset import DatasetManager
from core.exports import Exporter
from bot.queue_manager import QueueItem, QueueManager
from bot import ui
from utils.logger import get_logger
from utils.file_utils import ensure_dir

logger = get_logger(__name__)

_TELEGRAM_MAX_BYTES = 50 * 1024 * 1024   # 50 MB
_UPLOAD_MAX_RETRIES = 3
_UPLOAD_RETRY_DELAY = 5                   # seconds (doubles each attempt)


class BotHandlers:
    def __init__(self) -> None:
        cfg = get_settings()
        self._cfg = cfg

        self._db          = DatabaseManager(cfg.paths.db_file)
        self._audio_proc  = AudioProcessor(cfg.audio, cfg.paths.temp_dir)
        self._transcriber = Transcriber(cfg.transcription)
        self._dataset_mgr = DatasetManager(cfg.paths, cfg.splits)
        self._exporter    = Exporter(cfg.paths, cfg.paths.temp_dir)

        self._queue = QueueManager(max_workers=3, rebuild_debounce_s=10.0)
        self._queue.set_processor(self._process_item)
        self._queue.set_rebuild(self._rebuild_dataset)

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def on_startup(self) -> None:
        await self._queue.start()
        logger.info("BotHandlers ready (3 concurrent workers).")

    async def on_shutdown(self) -> None:
        await self._queue.stop()

    # ── /start ─────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        name = update.effective_user.first_name or "صديق"
        await update.effective_message.reply_text(
            ui.msg_welcome(name),
            parse_mode="Markdown",
            reply_markup=ui.main_keyboard(),
        )

    # ── /help ──────────────────────────────────────────────────────────────

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            ui.msg_help(), parse_mode="Markdown"
        )

    # ── text (keyboard buttons) ────────────────────────────────────────────

    async def handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text

        if text == "🎙 رفع صوت":
            await update.message.reply_text(
                "📥 *جاهز!*\nأرسل أو سجّل مقطعاً صوتياً الآن.",
                parse_mode="Markdown",
            )
        elif text == "⏳ حالة الطابور":
            await update.message.reply_text(
                ui.msg_queue_status(self._queue.depth, self._queue.active),
                parse_mode="Markdown",
            )
        elif text == "📊 إحصائيات":
            await self.cmd_stats(update, ctx)
        elif text == "❓ مساعدة":
            await self.cmd_help(update, ctx)
        elif text == "📞 التواصل مع الإدارة":
            await update.message.reply_text(
                ui.msg_contact(), parse_mode="Markdown"
            )

    # ── admin guard ────────────────────────────────────────────────────────

    def is_admin(self, user_id: int) -> bool:
        allowed = self._cfg.telegram.allowed_users
        return not allowed or user_id in allowed

    # ── /admin ─────────────────────────────────────────────────────────────

    async def cmd_admin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id):
            await update.effective_message.reply_text(
                ui.msg_unauthorized(), parse_mode="Markdown"
            )
            return
        await update.effective_message.reply_text(
            ui.msg_admin_panel(),
            parse_mode="Markdown",
            reply_markup=ui.admin_keyboard(),
        )

    # ── callback buttons ───────────────────────────────────────────────────

    async def handle_admin_callbacks(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not self.is_admin(update.effective_user.id):
            await query.answer(ui.msg_unauthorized(), show_alert=True)
            return
        await query.answer()

        if   query.data == "admin_stats":     await self.cmd_stats(update, ctx)
        elif query.data == "admin_export":    await self.cmd_export(update, ctx)
        elif query.data == "admin_rebuild":   await self.cmd_rebuild(update, ctx)
        elif query.data == "admin_logs":      await self.cmd_logs(update, ctx)
        elif query.data == "admin_broadcast":
            await query.message.reply_text(
                ui.msg_broadcast_guide(), parse_mode="Markdown"
            )

    # ── /logs ──────────────────────────────────────────────────────────────

    async def cmd_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id):
            return
        logs_dir  = Path(self._cfg.paths.logs_dir)
        log_files = sorted(logs_dir.glob("*.log"), key=os.path.getmtime, reverse=True)
        if not log_files:
            await update.effective_message.reply_text(
                ui.msg_no_logs(), parse_mode="Markdown"
            )
            return
        with open(log_files[0], "rb") as f:
            await ctx.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=log_files[0].name,
                caption=ui.msg_log_caption(),
                parse_mode="Markdown",
            )

    # ── /broadcast ─────────────────────────────────────────────────────────

    async def cmd_broadcast(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self.is_admin(update.effective_user.id):
            return
        if not ctx.args:
            await update.effective_message.reply_text(
                ui.msg_broadcast_guide(), parse_mode="Markdown"
            )
            return
        message = " ".join(ctx.args)
        await update.effective_message.reply_text("⏳ جارٍ الإرسال…")

        rows  = self._db.get_accepted()
        users: set[int] = set()
        for row in rows:
            uid = (
                row.get("telegram_user_id")
                if isinstance(row, dict)
                else getattr(row, "telegram_user_id", None)
            )
            if uid:
                users.add(uid)

        if not users:
            await update.effective_message.reply_text(
                ui.msg_broadcast_no_users(), parse_mode="Markdown"
            )
            return

        success = 0
        for uid in users:
            try:
                await ctx.bot.send_message(
                    chat_id=uid,
                    text=(
                        "📢 *رسالة إدارية*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"{message}"
                    ),
                    parse_mode="Markdown",
                )
                success += 1
            except Exception:
                pass

        await update.effective_message.reply_text(
            ui.msg_broadcast_done(success), parse_mode="Markdown"
        )

    # ── /stats ─────────────────────────────────────────────────────────────

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        stats = self._db.get_statistics()
        await update.effective_message.reply_text(
            ui.msg_stats(stats, self._queue.depth, self._queue.active),
            parse_mode="Markdown",
        )

    # ── /export ────────────────────────────────────────────────────────────

    async def cmd_export(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id):
            return
        stats    = self._db.get_statistics()
        accepted = stats["accepted_files"]
        if accepted == 0:
            await update.effective_message.reply_text(
                "⚠️ *لا توجد ملفات*\nقاعدة البيانات فارغة حتى الآن.",
                parse_mode="Markdown",
            )
            return

        await update.effective_message.reply_text(
            ui.msg_export_start(accepted), parse_mode="Markdown"
        )
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_DOCUMENT)

        zip_paths: list[Path] = []
        try:
            zip_paths   = self._exporter.create_zips(max_mb=40.0)
            total_parts = len(zip_paths)
            logger.info("Export: %d ZIP part(s), uploading…", total_parts)

            for i, zp in enumerate(zip_paths, 1):
                size_mb = zp.stat().st_size / (1024 * 1024)
                if zp.stat().st_size > _TELEGRAM_MAX_BYTES:
                    logger.error("ZIP part %s is %.2f MB — skipped.", zp.name, size_mb)
                    await update.effective_message.reply_text(
                        ui.msg_export_part_too_large(i, total_parts, size_mb),
                        parse_mode="Markdown",
                    )
                    continue
                await self._send_document_with_retry(
                    ctx=ctx,
                    chat_id=update.effective_chat.id,
                    file_path=zp,
                    caption=ui.msg_export_part_caption(i, total_parts, size_mb),
                )
                logger.info("Sent part %d/%d (%.2f MB)", i, total_parts, size_mb)

            await update.effective_message.reply_text(
                ui.msg_export_done(), parse_mode="Markdown"
            )
        except Exception as exc:
            logger.exception("Export failed")
            await update.effective_message.reply_text(
                ui.msg_export_error(str(exc)), parse_mode="Markdown"
            )
        finally:
            for zp in zip_paths:
                if zp and zp.exists():
                    try:
                        zp.unlink(missing_ok=True)
                    except Exception:
                        pass

    async def _send_document_with_retry(
        self,
        ctx: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        file_path: Path,
        caption: str,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, _UPLOAD_MAX_RETRIES + 1):
            try:
                with open(file_path, "rb") as fh:
                    await ctx.bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=file_path.name,
                        caption=caption,
                        parse_mode="Markdown",
                        read_timeout=600,
                        write_timeout=600,
                        connect_timeout=60,
                        pool_timeout=60,
                    )
                return
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
                last_exc = exc
            except (TimedOut, NetworkError) as exc:
                delay = _UPLOAD_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Upload attempt %d/%d failed (%s). Retry in %ds…",
                    attempt, _UPLOAD_MAX_RETRIES, exc, delay,
                )
                last_exc = exc
                if attempt < _UPLOAD_MAX_RETRIES:
                    await asyncio.sleep(delay)
            except Exception as exc:
                raise
        raise RuntimeError(
            f"فشل رفع '{file_path.name}' بعد {_UPLOAD_MAX_RETRIES} محاولات. "
            f"آخر خطأ: {last_exc}"
        ) from last_exc

    # ── /rebuild ───────────────────────────────────────────────────────────

    async def cmd_rebuild(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self.is_admin(update.effective_user.id):
            return
        await update.effective_message.reply_text(
            ui.msg_rebuild_start(), parse_mode="Markdown"
        )
        rows = self._db.get_accepted()
        self._dataset_mgr.rebuild(rows)
        stats = self._db.get_statistics()
        self._dataset_mgr.update_statistics(stats)
        await update.effective_message.reply_text(
            ui.msg_rebuild_done(stats["accepted_files"]), parse_mode="Markdown"
        )

    # ── audio received ─────────────────────────────────────────────────────

    async def handle_audio(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg  = update.message
        user = msg.from_user

        tg_file       = None
        original_name = "voice.oga"

        if msg.voice:
            tg_file       = msg.voice
            original_name = f"voice_{msg.message_id}.oga"
        elif msg.audio:
            tg_file       = msg.audio
            original_name = msg.audio.file_name or f"audio_{msg.message_id}.mp3"
        elif msg.document:
            doc = msg.document
            ext = (doc.file_name or "").rsplit(".", 1)[-1].lower()
            if ext in self._cfg.audio.supported_formats:
                tg_file       = doc
                original_name = doc.file_name or f"doc_{msg.message_id}.{ext}"
            else:
                await msg.reply_text(
                    ui.msg_unsupported_format(ext, self._cfg.audio.supported_formats),
                    parse_mode="Markdown",
                )
                return

        if not tg_file:
            return

        self._queue.enqueue(QueueItem(
            chat_id=msg.chat_id,
            user_id=user.id,
            user_name=user.full_name,
            file_id=tg_file.file_id,
            original_filename=original_name,
            message_id=msg.message_id,
        ))

        await msg.reply_text(
            ui.msg_file_received(original_name, self._queue.depth, self._queue.active),
            parse_mode="Markdown",
        )

    # ── item processor ─────────────────────────────────────────────────────

    async def _process_item(self, item: QueueItem, seq_lock: asyncio.Lock) -> None:
        cfg      = self._cfg
        temp_dir = ensure_dir(cfg.paths.temp_dir)
        raw_path = temp_dir / f"{item.message_id}_{item.original_filename}"
        bot_app  = self._get_bot_app()

        # 1. Download
        try:
            tg_file = await bot_app.bot.get_file(item.file_id)
            await tg_file.download_to_drive(str(raw_path))
        except Exception as exc:
            await bot_app.bot.send_message(
                item.chat_id,
                ui.msg_download_error(item.original_filename, str(exc)),
                parse_mode="Markdown",
            )
            return

        # 2. Duplicate check (raw)
        from utils.file_utils import compute_sha256
        raw_hash = compute_sha256(raw_path)
        if self._db.hash_exists(raw_hash):
            raw_path.unlink(missing_ok=True)
            await bot_app.bot.send_message(
                item.chat_id,
                ui.msg_duplicate(item.original_filename),
                parse_mode="Markdown",
            )
            return

        # 3. Audio processing
        wav_path     = temp_dir / f"proc_{item.message_id}.wav"
        audio_result = self._audio_proc.process(raw_path, wav_path)
        raw_path.unlink(missing_ok=True)

        if not audio_result.success:
            self._save_rejected(item, audio_result, raw_hash)
            await bot_app.bot.send_message(
                item.chat_id,
                ui.msg_rejected(item.original_filename, audio_result.rejection_reason or ""),
                parse_mode="Markdown",
            )
            return

        # 4. Duplicate check (processed)
        if self._db.hash_exists(audio_result.file_hash):
            wav_path.unlink(missing_ok=True)
            await bot_app.bot.send_message(
                item.chat_id,
                ui.msg_duplicate(item.original_filename),
                parse_mode="Markdown",
            )
            return

        # 5. Transcription
        trans_result = self._transcriber.transcribe(audio_result.output_path)
        if not trans_result.success:
            wav_path.unlink(missing_ok=True)
            self._save_rejected(
                item, audio_result,
                audio_result.file_hash,
                rejection_reason=trans_result.rejection_reason,
            )
            await bot_app.bot.send_message(
                item.chat_id,
                ui.msg_rejected(item.original_filename, trans_result.rejection_reason or ""),
                parse_mode="Markdown",
            )
            return

        # 6. CRITICAL SECTION — filename reservation + move + insert (<50 ms)
        async with seq_lock:
            wav_filename = self._db.next_filename()
            final_wav    = cfg.paths.original_dir / wav_filename
            final_wav.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(wav_path), str(final_wav))
            self._db.insert_record(
                filename=wav_filename,
                original_filename=item.original_filename,
                transcript=trans_result.text,
                duration=audio_result.duration_seconds,
                language=trans_result.language,
                sample_rate=audio_result.sample_rate,
                channels=audio_result.channels,
                confidence=trans_result.confidence,
                file_hash=audio_result.file_hash,
                file_size=audio_result.file_size_bytes,
                processing_status="accepted",
                telegram_user_id=item.user_id,
                telegram_file_id=item.file_id,
            )

        # 7. Schedule debounced rebuild
        self._queue.notify_rebuild_needed()

        # 8. Notify user
        stats      = self._db.get_statistics()
        short_text = (
            trans_result.text[:80] + "…"
            if len(trans_result.text) > 80
            else trans_result.text
        )
        await bot_app.bot.send_message(
            item.chat_id,
            ui.msg_accepted(
                wav_filename, short_text,
                audio_result.duration_seconds,
                trans_result.confidence,
                stats["accepted_files"],
            ),
            parse_mode="Markdown",
        )

    # ── debounced rebuild ──────────────────────────────────────────────────

    async def _rebuild_dataset(self) -> None:
        rows  = self._db.get_accepted()
        loop  = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._dataset_mgr.rebuild, rows)
        stats = self._db.get_statistics()
        await loop.run_in_executor(None, self._dataset_mgr.update_statistics, stats)
        logger.info("Dataset rebuilt: %d accepted files.", stats["accepted_files"])

    # ── helpers ────────────────────────────────────────────────────────────

    def _save_rejected(
        self,
        item: QueueItem,
        audio_result,
        file_hash: str,
        rejection_reason: Optional[str] = None,
    ) -> None:
        self._db.insert_record(
            filename=f"rejected_{item.message_id}.wav",
            original_filename=item.original_filename,
            transcript="",
            duration=audio_result.duration_seconds,
            language="unknown",
            sample_rate=audio_result.sample_rate,
            channels=audio_result.channels,
            confidence=0.0,
            file_hash=file_hash,
            file_size=audio_result.file_size_bytes,
            processing_status="rejected",
            rejection_reason=rejection_reason or audio_result.rejection_reason or "unknown",
            telegram_user_id=item.user_id,
            telegram_file_id=item.file_id,
        )

    _bot_app = None

    def set_bot_app(self, app) -> None:
        self.__class__._bot_app = app

    def _get_bot_app(self):
        return self.__class__._bot_app
