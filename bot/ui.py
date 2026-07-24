"""
UI Templates  —  Libyan ASR Dataset Builder Bot
================================================
Central module for all user-facing message text, formatting helpers,
and keyboard layouts.  Keeping messages here means we never scatter
Arabic strings and emoji across the codebase.

Design language
---------------
• Arabic-first, right-aligned feel inside Markdown blocks
• Consistent dividers using  ━━━  and  ─────
• Progress bars with Unicode blocks  █▓░
• Bold headers + structured key–value lines
• Buttons arranged in logical clusters (not a flat list)
"""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


# ── Progress bar helper ────────────────────────────────────────────────────

def progress_bar(value: int, total: int, width: int = 12) -> str:
    """Return a Unicode block progress bar like  ████████░░░░  (62%)."""
    if total <= 0:
        return "░" * width
    filled = round(width * value / total)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def pct(value: int, total: int) -> str:
    return f"{round(value / total * 100)}%" if total > 0 else "0%"


# ── Main keyboard ──────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    keys = [
        [KeyboardButton("🎙 رفع صوت"),          KeyboardButton("⏳ حالة الطابور")],
        [KeyboardButton("📊 إحصائيات"),          KeyboardButton("❓ مساعدة")],
        [KeyboardButton("📞 التواصل مع الإدارة")],
    ]
    return ReplyKeyboardMarkup(
        keys, resize_keyboard=True,
        input_field_placeholder="اختر أو أرسل ملفاً صوتياً…",
    )


# ── Admin inline keyboard ──────────────────────────────────────────────────

def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات",          callback_data="admin_stats")],
        [
            InlineKeyboardButton("📦 تصدير ZIP",         callback_data="admin_export"),
            InlineKeyboardButton("🔄 إعادة البناء",       callback_data="admin_rebuild"),
        ],
        [InlineKeyboardButton("📑 سجل الأخطاء",          callback_data="admin_logs")],
        [InlineKeyboardButton("📢 بث رسالة للجميع",       callback_data="admin_broadcast")],
    ])


# ── Welcome / start ────────────────────────────────────────────────────────

def msg_welcome(first_name: str) -> str:
    return (
        "🎙 *Libyan ASR Dataset Builder*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"أهلاً *{first_name}* 👋\n\n"
        "أنا بوت بناء قاعدة البيانات الصوتية الليبية.\n"
        "أرسل أي مقطع صوتي وسأتولى المعالجة تلقائياً ✨\n\n"
        "📌 *كيف يعمل البوت:*\n"
        "① أرسل مقطعاً صوتياً أو ملفاً\n"
        "② أقوم بتحويله إلى WAV نظيف\n"
        "③ أنسخ النص تلقائياً بالذكاء الاصطناعي\n"
        "④ يُحفظ في قاعدة البيانات مباشرةً\n\n"
        "👇 استخدم الأزرار أدناه للبدء"
    )


# ── Help ───────────────────────────────────────────────────────────────────

def msg_help() -> str:
    return (
        "❓ *دليل الاستخدام*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎙 *إرسال الصوت*\n"
        "   سجّل مقطعاً مباشرةً أو ارفع ملفاً\n"
        "   الصيغ المقبولة: OGG · MP3 · WAV · M4A · FLAC\n\n"
        "⏱ *المدة المسموحة*\n"
        "   من ٠٫٥ ثانية حتى ٣٠ ثانية\n\n"
        "🔬 *معالجة تلقائية*\n"
        "   • تحويل إلى 16kHz أحادي 16-bit\n"
        "   • إزالة الصمت من الأطراف\n"
        "   • تطبيع مستوى الصوت\n"
        "   • نسخ النص بالذكاء الاصطناعي\n\n"
        "🔁 *الملفات المكررة*\n"
        "   يتم تجاهلها تلقائياً باستخدام SHA-256\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "للدعم: اضغط *📞 التواصل مع الإدارة*"
    )


# ── Queue status (text button) ─────────────────────────────────────────────

def msg_queue_status(waiting: int, active: int) -> str:
    if waiting == 0 and active == 0:
        return (
            "✅ *الطابور فارغ*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "البوت متفرغ تماماً وجاهز لاستقبال ملفات جديدة 🟢"
        )
    bar_w = progress_bar(active, active + waiting, width=10)
    return (
        "⏳ *حالة الطابور*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⚡ قيد المعالجة : `{active}` ملف\n"
        f"📋 في الانتظار  : `{waiting}` ملف\n"
        f"📊 التقدم       : `{bar_w}`"
    )


# ── File received ──────────────────────────────────────────────────────────

def msg_file_received(filename: str, position: int, active: int) -> str:
    if position == 0:
        pos_line = "📡 *الملف قيد المعالجة الآن…*"
    else:
        pos_line = f"📋 موضعك في الطابور: *{position}*"
    active_line = f"⚡ يُعالَج حالياً: `{active}` ملف بالتوازي" if active > 0 else ""
    return (
        "📥 *تم استلام ملفك*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔖 الملف   : `{filename}`\n"
        f"{pos_line}\n"
        + (f"{active_line}\n" if active_line else "")
        + "\n_سيصلك إشعار فور اكتمال المعالجة_ 🔔"
    )


# ── Processing result: accepted ────────────────────────────────────────────

def msg_accepted(
    wav_filename: str,
    short_text: str,
    duration: float,
    confidence: float,
    total_accepted: int,
) -> str:
    conf_bar = progress_bar(round(confidence * 10), 10, width=10)
    return (
        "✅ *تمت المعالجة بنجاح!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 الملف     : `{wav_filename}`\n"
        f"📝 النص      : _{short_text}_\n"
        f"⏱ المدة     : `{duration:.1f}` ثانية\n"
        f"🎯 الدقة     : `{conf_bar}` {confidence:.0%}\n"
        "─────────────────────────────\n"
        f"📊 إجمالي المقبولة: *{total_accepted}* ملف"
    )


# ── Processing result: rejected ────────────────────────────────────────────

def msg_rejected(filename: str, reason: str) -> str:
    return (
        "❌ *رُفض الملف*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔖 الملف  : `{filename}`\n"
        f"⚠️ السبب  : {reason}\n\n"
        "_تأكد من أن الصوت يحتوي على كلام واضح\n"
        "ومدته بين ٠٫٥ و٣٠ ثانية._"
    )


# ── Duplicate ─────────────────────────────────────────────────────────────

def msg_duplicate(filename: str) -> str:
    return (
        "🔁 *ملف مكرر*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔖 الملف  : `{filename}`\n"
        "ℹ️ هذا الملف موجود مسبقاً في قاعدة البيانات.\n"
        "_تم تجاهله تلقائياً لتجنب التكرار._"
    )


# ── Download error ─────────────────────────────────────────────────────────

def msg_download_error(filename: str, error: str) -> str:
    return (
        "⚠️ *فشل تنزيل الملف*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔖 الملف  : `{filename}`\n"
        f"🔴 الخطأ  : `{error}`\n\n"
        "_يرجى إعادة إرسال الملف مجدداً._"
    )


# ── Unsupported format ─────────────────────────────────────────────────────

def msg_unsupported_format(ext: str, supported: list[str]) -> str:
    fmt_list = " · ".join(f.upper() for f in supported)
    return (
        "⛔ *صيغة غير مدعومة*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔖 الصيغة المرسلة : `.{ext}`\n\n"
        "📋 *الصيغ المقبولة:*\n"
        f"`{fmt_list}`"
    )


# ── Stats ──────────────────────────────────────────────────────────────────

def msg_stats(stats: dict, waiting: int, active: int) -> str:
    total     = stats["total_files"]
    accepted  = stats["accepted_files"]
    rejected  = stats["rejected_files"]
    hours     = stats["total_duration_hours"]
    avg_s     = stats["average_duration_seconds"]

    # Human-readable size
    raw = stats["total_size_bytes"]
    if raw >= 1_073_741_824:
        size_str = f"{raw / 1_073_741_824:.2f} GB"
    elif raw >= 1_048_576:
        size_str = f"{raw / 1_048_576:.1f} MB"
    elif raw >= 1024:
        size_str = f"{raw / 1024:.0f} KB"
    else:
        size_str = f"{raw} B"

    acc_bar = progress_bar(accepted, total) if total else "░" * 12
    rej_bar = progress_bar(rejected, total) if total else "░" * 12

    return (
        "📊 *إحصائيات قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"📁 إجمالي الملفات  : *{total}*\n\n"
        f"✅ مقبولة  `{acc_bar}` *{accepted}* ({pct(accepted, total)})\n"
        f"❌ مرفوضة  `{rej_bar}` *{rejected}* ({pct(rejected, total)})\n"
        "──────────────────────────────\n"
        f"⏱ المدة الكلية    : *{hours:.2f}* ساعة\n"
        f"📏 متوسط المدة    : *{avg_s:.1f}* ثانية\n"
        f"💾 الحجم الكلي    : *{size_str}*\n"
        "══════════════════════════════\n"
        f"⚡ قيد المعالجة   : *{active}* ملف\n"
        f"⏳ في الانتظار    : *{waiting}* ملف"
    )


# ── Admin panel ────────────────────────────────────────────────────────────

def msg_admin_panel() -> str:
    return (
        "⚙️ *لوحة تحكم الإدارة*\n"
        "══════════════════════════════\n"
        "اختر الإجراء المطلوب من الأزرار أدناه:\n\n"
        "📊 *الإحصائيات* — عرض تقرير كامل\n"
        "📦 *تصدير ZIP* — تصدير قاعدة البيانات\n"
        "🔄 *إعادة البناء* — إعادة بناء ملفات CSV/JSON\n"
        "📑 *السجل* — تنزيل آخر ملف سجل\n"
        "📢 *البث* — إرسال رسالة لجميع المستخدمين"
    )


# ── Export messages ────────────────────────────────────────────────────────

def msg_export_start(accepted: int) -> str:
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 الملفات المقبولة : *{accepted}* ملف صوتي\n\n"
        "⏳ _جارٍ تجهيز الأجزاء…_"
    )


def msg_export_building() -> str:
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🗜 جارٍ ضغط الملفات وتقسيمها إلى أجزاء…\n\n"
        "⏳ _قد يستغرق ذلك بضع دقائق حسب حجم القاعدة_"
    )


def msg_export_uploading(part: int, total: int, size_mb: float) -> str:
    bar = progress_bar(part - 1, total, width=10)
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 يُرفع الجزء  : *{part}* من *{total}*\n"
        f"💾 الحجم        : *{size_mb:.1f} MB*\n"
        f"📊 التقدم       : `{bar}` {part - 1}/{total}\n\n"
        "⏳ _جارٍ الرفع إلى تيليجرام…_"
    )


def msg_export_part_caption(part: int, total: int, size_mb: float) -> str:
    return (
        f"📦 *Libyan ASR Dataset — الجزء {part}/{total}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💾 الحجم : *{size_mb:.1f} MB*"
    )


def msg_export_done(sent: int, total: int, skipped: list | None = None) -> str:
    skipped = skipped or []
    skip_note = ""
    if skipped:
        skip_note = (
            "\n\n⚠️ *ملفات تعذّر إرسالها (حجمها يتجاوز ٥٠ MB حتى بعد الضغط):*\n"
            + "\n".join(f"  • `{s}`" for s in skipped)
        )
    return (
        "🎉 *اكتمل التصدير!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ تم إرسال *{sent}* من أصل *{total}* جزء بنجاح.\n"
        "_يمكنك الآن تنزيل الملفات واستخدامها._"
        + skip_note
    )


def msg_export_part_too_large(part: int, total: int, size_mb: float) -> str:
    # Kept for backward compatibility; not used in the new flow.
    return (
        f"⚠️ *الجزء {part}/{total} كبير جداً ({size_mb:.1f} MB)*\n"
        "_تم تخطيه — تحقق من السجل._"
    )


def msg_export_error(error: str) -> str:
    return (
        "🔴 *فشل التصدير*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ الخطأ : `{error}`\n\n"
        "_يرجى المحاولة مجدداً أو مراجعة السجل._"
    )


# ── Rebuild ────────────────────────────────────────────────────────────────

def msg_rebuild_start() -> str:
    return (
        "🔄 *إعادة بناء ملفات Dataset*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ جارٍ إعادة بناء ملفات CSV / JSON…"
    )


def msg_rebuild_done(accepted: int) -> str:
    return (
        "✅ *اكتملت إعادة البناء*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 إجمالي الملفات المقبولة: *{accepted}* ملف\n"
        "_تم تحديث metadata.csv و dataset.json بنجاح._"
    )


# ── Broadcast ─────────────────────────────────────────────────────────────

def msg_broadcast_guide() -> str:
    return (
        "📢 *بث رسالة للجميع*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "اكتب الأمر التالي:\n"
        "`/broadcast نص الرسالة هنا`\n\n"
        "مثال:\n"
        "`/broadcast شكراً لمساهمتكم! تم الوصول لـ ٥٠٠ ملف صوتي 🎉`"
    )


def msg_broadcast_done(success: int) -> str:
    return (
        "📢 *اكتمل البث*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ تم الإرسال بنجاح إلى *{success}* مستخدم"
    )


def msg_broadcast_no_users() -> str:
    return (
        "⚠️ *لا يوجد مستخدمون*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "لم يتم العثور على مستخدمين مسجلين في قاعدة البيانات."
    )


# ── Contact ────────────────────────────────────────────────────────────────

def msg_contact() -> str:
    return (
        "📞 *التواصل مع الإدارة*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "للتواصل أو الإبلاغ عن مشكلة:\n"
        "راسلنا على الحساب المخصص للإدارة.\n\n"
        "_سيتم الرد في أقرب وقت ممكن_ 🕐"
    )


# ── Logs ───────────────────────────────────────────────────────────────────

def msg_no_logs() -> str:
    return (
        "⚠️ *لا توجد سجلات*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "لم يتم العثور على ملفات سجل (Logs) حتى الآن."
    )


def msg_log_caption() -> str:
    return "📑 *أحدث سجل للأخطاء*\n_تم تنزيله من الخادم_ 🖥"


# ── Unauthorized ───────────────────────────────────────────────────────────

def msg_unauthorized() -> str:
    return "⛔ *غير مصرح*\nهذا الأمر مخصص للإدارة فقط."


# ── Upload states ──────────────────────────────────────────────────────────

def msg_upload_retry(attempt: int, total: int, error: str, delay: int) -> str:
    bar = progress_bar(attempt, total, width=8)
    return (
        f"🔁 *إعادة محاولة الرفع*  `{bar}` {attempt}/{total}\n"
        f"⚠️ الخطأ  : `{error}`\n"
        f"⏳ الانتظار: {delay} ثانية…"
    )
