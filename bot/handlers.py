"""
Bot Handlers
============
All Telegram command and message handlers live here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config.settings import get_settings
from core.audio import AudioProcessor
from core.speech import Transcriber
from core.database import DatabaseManager
from core.dataset import DatasetManager
from core.exports import Exporter
from bot.queue_manager import QueueItem, QueueManager
from utils.logger import get_logger
from utils.file_utils import ensure_dir, human_readable_size

logger = get_logger(__name__)


class BotHandlers:
    def __init__(self) -> None:
        cfg = get_settings()
        self._cfg = cfg

        self._db = DatabaseManager(cfg.paths.db_file)
        self._audio_proc = AudioProcessor(cfg.audio, cfg.paths.temp_dir)
        self._transcriber = Transcriber(cfg.transcription)
        self._dataset_mgr = DatasetManager(cfg.paths, cfg.splits)
        self._exporter = Exporter(cfg.paths, cfg.paths.temp_dir)
        self._queue = QueueManager()
        self._queue.set_processor(self._process_item)

    async def on_startup(self) -> None:
        await self._queue.start()
        logger.info("BotHandlers startup complete.")

    async def on_shutdown(self) -> None:
        await self._queue.stop()

    # ── /start ─────────────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "🎙 *مرحباً بك في Libyan ASR Dataset Builder*\n\n"
            "أنا هنا لمساعدتك في بناء قاعدة البيانات الصوتية.\n"
            "فقط قم برفع أي مقطع صوتي وسأقوم بمعالجته فوراً! 🚀\n\n"
            "👇 *اختر من القائمة أدناه:*"
        )
        
        keyboard = [
            [KeyboardButton("رفع ملف صوتي 🎙"), KeyboardButton("حالة المعالجة ⏳")],
            [KeyboardButton("إحصائياتي 📊"), KeyboardButton("المساعدة ❓")],
            [KeyboardButton("📞 التواصل مع الإدارة")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="اختر إجراءً...")

        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    # ── /help ──────────────────────────────────────────────────────────────
    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "❓ *دليل الاستخدام:*\n\n"
            "1️⃣ *لإضافة صوت:* فقط قم بتسجيل مقطع صوتي وإرساله، أو ارفع ملف (MP3, WAV, OGG).\n"
            "2️⃣ *المدة المسموحة:* لا تقل عن ثانية ولا تزيد عن 30 ثانية.\n"
            "3️⃣ *الجودة:* البوت سيقوم بتنقية الصوت وتعديل التردد تلقائياً.\n\n"
            "لأي استفسار إضافي، استخدم زر 'التواصل مع الإدارة'."
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    # ── معالجة النصوص ──────────────────────────────────────────────────────
    async def handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text

        if text == "رفع ملف صوتي 🎙":
            await update.message.reply_text("📥 أنا جاهز! فقط قم بتسجيل مقطع صوتي أو إرسال ملف صوتي الآن.")
        elif text == "حالة المعالجة ⏳":
            queue_depth = self._queue.depth
            if queue_depth == 0:
                await update.message.reply_text("✅ لا يوجد أي ملفات في طابور الانتظار. البوت متفرغ تماماً.")
            else:
                await update.message.reply_text(f"⏳ يوجد حالياً {queue_depth} ملف/ملفات في طابور المعالجة.")
        elif text == "إحصائياتي 📊":
            await self.cmd_stats(update, ctx)
        elif text == "المساعدة ❓":
            await self.cmd_help(update, ctx)
        elif text == "📞 التواصل مع الإدارة":
            await update.message.reply_text("📩 للتواصل مع الإدارة أو الإبلاغ عن مشكلة، راسلنا على الحساب المخصص.")

    # ── حماية أوامر الإدارة ────────────────────────────────────────────────
    def is_admin(self, user_id: int) -> bool:
        allowed = self._cfg.telegram.allowed_users
        return not allowed or user_id in allowed

    # ── /admin (لوحة تحكم المدير) ──────────────────────────────────────────
    async def cmd_admin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔️ هذا الأمر مخصص للإدارة فقط.")
            return

        keyboard = [
            [InlineKeyboardButton("📊 إحصائيات القاعدة", callback_data="admin_stats")],
            [InlineKeyboardButton("📦 تصدير (Export)", callback_data="admin_export"), InlineKeyboardButton("🔄 صيانة (Rebuild)", callback_data="admin_rebuild")],
            [InlineKeyboardButton("📑 سحب سجل الأخطاء (Logs)", callback_data="admin_logs")],
            [InlineKeyboardButton("📢 إرسال رسالة للجميع (Broadcast)", callback_data="admin_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text("⚙️ *لوحة تحكم الإدارة*\nاختر الإجراء المطلوب من الأزرار:", parse_mode="Markdown", reply_markup=reply_markup)

    # ── استجابة أزرار لوحة التحكم ──────────────────────────────────────────
    async def handle_admin_callbacks(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self.is_admin(update.effective_user.id):
            await query.answer("⛔️ غير مصرح لك.", show_alert=True)
            return

        await query.answer()

        if query.data == "admin_stats":
            await self.cmd_stats(update, ctx)
        elif query.data == "admin_export":
            await self.cmd_export(update, ctx)
        elif query.data == "admin_rebuild":
            await self.cmd_rebuild(update, ctx)
        elif query.data == "admin_logs":
            await self.cmd_logs(update, ctx)
        elif query.data == "admin_broadcast":
            await query.message.reply_text("📢 *لإرسال رسالة لجميع المستخدمين:*\nاكتب الأمر `/broadcast` متبوعاً برسالتك.\n\nمثال:\n`/broadcast السلام عليكم، هناك تحديث جديد!`", parse_mode="Markdown")

    # ── /logs (سحب سجل الأخطاء) ────────────────────────────────────────────
    async def cmd_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id): return
        
        logs_dir = Path(self._cfg.paths.logs_dir)
        log_files = sorted(logs_dir.glob("*.log"), key=os.path.getmtime, reverse=True)
        
        if not log_files:
            await update.effective_message.reply_text("⚠️ لا توجد ملفات سجل (Logs) حالياً.")
            return
            
        latest_log = log_files[0]
        with open(latest_log, "rb") as f:
            await ctx.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f, 
                filename=latest_log.name, 
                caption="📑 أحدث سجل للأخطاء (Logs)"
            )

    # ── /broadcast (إذاعة رسالة) ───────────────────────────────────────────
    async def cmd_broadcast(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id): return
        
        if not ctx.args:
            await update.effective_message.reply_text("⚠️ يرجى كتابة الرسالة بعد الأمر.\nمثال: `/broadcast أهلاً بكم`", parse_mode="Markdown")
            return
            
        message = " ".join(ctx.args)
        await update.effective_message.reply_text("⏳ جاري إرسال الرسالة...")
        
        # استخراج المستخدمين من قاعدة البيانات
        rows = self._db.get_accepted()
        users = set()
        for row in rows:
            uid = row.get("telegram_user_id") if isinstance(row, dict) else getattr(row, "telegram_user_id", None)
            if uid:
                users.add(uid)
                
        if not users:
            await update.effective_message.reply_text("⚠️ لم يتم العثور على مستخدمين مسجلين لإرسال الرسالة.")
            return

        success = 0
        for uid in users:
            try:
                await ctx.bot.send_message(chat_id=uid, text=f"📢 *رسالة إدارية:*\n\n{message}", parse_mode="Markdown")
                success += 1
            except Exception:
                pass # المستخدم قد يكون حظر البوت
                
        await update.effective_message.reply_text(f"✅ تم الإرسال بنجاح إلى {success} مستخدم.")

    # ── /stats ─────────────────────────────────────────────────────────────
    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        stats = self._db.get_statistics()
        self._dataset_mgr.update_statistics(stats)
        hours = stats["total_duration_hours"]
        avg_s = stats["average_duration_seconds"]
        size = human_readable_size(stats["total_size_bytes"])
        queue_depth = self._queue.depth

        text = (
            "📊 *إحصائيات قاعدة البيانات*\n\n"
            f"📁 إجمالي الملفات   : {stats['total_files']}\n"
            f"✅ مقبولة           : {stats['accepted_files']}\n"
            f"❌ مرفوضة          : {stats['rejected_files']}\n"
            f"⏱ إجمالي المدة    : {hours:.2f} ساعة\n"
            f"📏 متوسط المدة     : {avg_s:.1f} ثانية\n"
            f"💾 المساحة المستخدمة: {size}\n"
            f"⏳ في الانتظار     : {queue_depth} ملف"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    # ── /export ────────────────────────────────────────────────────────────
    async def cmd_export(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id): return
        stats = self._db.get_statistics()
        accepted = stats["accepted_files"]

        if accepted == 0:
            await update.effective_message.reply_text("⚠️ لا توجد ملفات مقبولة في قاعدة البيانات بعد.")
            return

        await update.effective_message.reply_text(f"📦 جاري إنشاء ملف ZIP يحتوي على {accepted} ملف صوتي…\nقد يستغرق هذا بعض الوقت.")
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_DOCUMENT)

        zip_path: Optional[Path] = None
        try:
            zip_path = self._exporter.create_zip()
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            with open(zip_path, "rb") as f:
                await ctx.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=zip_path.name,
                    caption=f"✅ *Libyan ASR Dataset*\nالملفات: {accepted}\nالحجم: {size_mb:.1f} MB",
                    parse_mode="Markdown",
                    read_timeout=120, write_timeout=120, connect_timeout=120
                )
        except Exception as exc:
            logger.exception("Export failed")
            await update.effective_message.reply_text(f"❌ خطأ أثناء التصدير: {exc}")
        finally:
            if zip_path and zip_path.exists():
                zip_path.unlink(missing_ok=True)

    # ── /rebuild ───────────────────────────────────────────────────────────
    async def cmd_rebuild(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_admin(update.effective_user.id): return
        await update.effective_message.reply_text("🔄 جاري إعادة بناء ملفات Dataset…")
        rows = self._db.get_accepted()
        self._dataset_mgr.rebuild(rows)
        stats = self._db.get_statistics()
        self._dataset_mgr.update_statistics(stats)
        await update.effective_message.reply_text(f"✅ تم إعادة البناء بنجاح.\n📁 إجمالي الملفات المقبولة: {stats['accepted_files']}")

    # ── audio file received ────────────────────────────────────────────────
    async def handle_audio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        user = msg.from_user

        # السماح للجميع بالمشاركة ما داموا لم يحظروا من القائمة (لو أردت حظر الجميع اترك القائمة فارغة)
        tg_file = None
        original_name = "voice.oga"

        if msg.voice:
            tg_file = msg.voice
            original_name = f"voice_{msg.message_id}.oga"
        elif msg.audio:
            tg_file = msg.audio
            original_name = msg.audio.file_name or f"audio_{msg.message_id}.mp3"
        elif msg.document:
            doc = msg.document
            ext = (doc.file_name or "").rsplit(".", 1)[-1].lower()
            if ext in self._cfg.audio.supported_formats:
                tg_file = doc
                original_name = doc.file_name or f"doc_{msg.message_id}.{ext}"
            else:
                await msg.reply_text(f"⚠️ الصيغة `.{ext}` غير مدعومة.\nالصيغ المدعومة: {', '.join(self._cfg.audio.supported_formats)}")
                return

        if not tg_file: return

        queue_depth = self._queue.enqueue(QueueItem(
            chat_id=msg.chat_id, user_id=user.id, user_name=user.full_name,
            file_id=tg_file.file_id, original_filename=original_name, message_id=msg.message_id
        ))

        await msg.reply_text(f"✅ تم استلام الملف: `{original_name}`\n⏳ موضعك في الطابور: {queue_depth}", parse_mode="Markdown")

    async def _process_item(self, item: QueueItem) -> None:
        cfg = self._cfg
        temp_dir = ensure_dir(cfg.paths.temp_dir)
        raw_path = temp_dir / f"{item.message_id}_{item.original_filename}"
        bot_app = self._get_bot_app()

        try:
            tg_file = await bot_app.bot.get_file(item.file_id)
            await tg_file.download_to_drive(str(raw_path))
        except Exception as exc:
            await bot_app.bot.send_message(item.chat_id, f"❌ فشل تنزيل الملف `{item.original_filename}`: {exc}", parse_mode="Markdown")
            return

        from utils.file_utils import compute_sha256
        raw_hash = compute_sha256(raw_path)
        if self._db.hash_exists(raw_hash):
            raw_path.unlink(missing_ok=True)
            await bot_app.bot.send_message(item.chat_id, f"⚠️ الملف `{item.original_filename}` مكرر — تم تجاهله.", parse_mode="Markdown")
            return

        wav_filename = self._db.next_filename()
        wav_path = temp_dir / wav_filename

        audio_result = self._audio_proc.process(raw_path, wav_path)
        raw_path.unlink(missing_ok=True)

        if not audio_result.success:
            self._save_rejected(item, audio_result, raw_hash)
            await bot_app.bot.send_message(item.chat_id, f"❌ رُفض الملف `{item.original_filename}`\nالسبب: {audio_result.rejection_reason}", parse_mode="Markdown")
            return

        if self._db.hash_exists(audio_result.file_hash):
            wav_path.unlink(missing_ok=True)
            await bot_app.bot.send_message(item.chat_id, f"⚠️ الملف `{item.original_filename}` مكرر بعد المعالجة — تم تجاهله.", parse_mode="Markdown")
            return

        trans_result = self._transcriber.transcribe(audio_result.output_path)

        if not trans_result.success:
            wav_path.unlink(missing_ok=True)
            self._save_rejected(item, audio_result, audio_result.file_hash, rejection_reason=trans_result.rejection_reason)
            await bot_app.bot.send_message(item.chat_id, f"❌ رُفض الملف `{item.original_filename}`\nالسبب: {trans_result.rejection_reason}", parse_mode="Markdown")
            return

        final_wav = cfg.paths.original_dir / wav_filename
        final_wav.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(wav_path), str(final_wav))

        self._db.insert_record(
            filename=wav_filename, original_filename=item.original_filename,
            transcript=trans_result.text, duration=audio_result.duration_seconds,
            language=trans_result.language, sample_rate=audio_result.sample_rate,
            channels=audio_result.channels, confidence=trans_result.confidence,
            file_hash=audio_result.file_hash, file_size=audio_result.file_size_bytes,
            processing_status="accepted", telegram_user_id=item.user_id, telegram_file_id=item.file_id
        )

        rows = self._db.get_accepted()
        self._dataset_mgr.rebuild(rows)
        stats = self._db.get_statistics()
        self._dataset_mgr.update_statistics(stats)

        dur = audio_result.duration_seconds
        conf = trans_result.confidence
        short_text = trans_result.text[:80] + "…" if len(trans_result.text) > 80 else trans_result.text
        
        await bot_app.bot.send_message(
            item.chat_id,
            f"✅ تمت المعالجة: `{wav_filename}`\n📝 النص: _{short_text}_\n⏱ المدة: {dur:.1f}s | 🎯 الثقة: {conf:.0%}\n📁 إجمالي الملفات: {stats['accepted_files']}",
            parse_mode="Markdown"
        )

    def _save_rejected(self, item: QueueItem, audio_result, file_hash: str, rejection_reason: Optional[str] = None) -> None:
        reason = rejection_reason or audio_result.rejection_reason or "unknown"
        self._db.insert_record(
            filename=f"rejected_{item.message_id}.wav", original_filename=item.original_filename,
            transcript="", duration=audio_result.duration_seconds, language="unknown",
            sample_rate=audio_result.sample_rate, channels=audio_result.channels,
            confidence=0.0, file_hash=file_hash, file_size=audio_result.file_size_bytes,
            processing_status="rejected", rejection_reason=reason,
            telegram_user_id=item.user_id, telegram_file_id=item.file_id
        )

    _bot_app = None
    def set_bot_app(self, app) -> None:
        self.__class__._bot_app = app
    def _get_bot_app(self):
        return self.__class__._bot_app