"""
UI Templates  —  Libyan ASR Dataset Builder Bot
================================================
Central module for all user-facing message text, formatting helpers,
and keyboard layouts.

Design language  (v4 — polished)
---------------------------------
• Arabic-first, right-aligned feel
• Layered dividers: ══  for section headers, ──  for sub-rows
• Animated-feel progress using multi-step Unicode blocks  ▏▎▍▌▋▊▉█
• Consistent icon language per action class
• Status messages always end with an action-hint line
"""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def progress_bar(value: int, total: int, width: int = 12) -> str:
    """Smooth Unicode block progress bar: ████████░░░░"""
    if total <= 0:
        return "░" * width
    filled = round(width * value / total)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def spinner_bar(step: int, width: int = 10) -> str:
    """Cycling fill bar that looks 'animated' when edited repeatedly."""
    fill = (step % (width + 1))
    return "█" * fill + "░" * (width - fill)


def pct(value: int, total: int) -> str:
    return f"{round(value / total * 100)}%" if total > 0 else "─"


def _size_str(raw_bytes: int) -> str:
    if raw_bytes >= 1_073_741_824:
        return f"{raw_bytes / 1_073_741_824:.2f} GB"
    if raw_bytes >= 1_048_576:
        return f"{raw_bytes / 1_048_576:.1f} MB"
    if raw_bytes >= 1024:
        return f"{raw_bytes / 1024:.0f} KB"
    return f"{raw_bytes} B"


# ═══════════════════════════════════════════════════════════════════════════
# Keyboards
# ═══════════════════════════════════════════════════════════════════════════

def main_keyboard() -> ReplyKeyboardMarkup:
    keys = [
        [KeyboardButton("🎙 رفع صوت"),           KeyboardButton("⏳ حالة الطابور")],
        [KeyboardButton("📊 إحصائيات"),           KeyboardButton("❓ مساعدة")],
        [KeyboardButton("📞 التواصل مع الإدارة")],
    ]
    return ReplyKeyboardMarkup(
        keys,
        resize_keyboard=True,
        input_field_placeholder="🎙 أرسل مقطعاً صوتياً أو اضغط زراً…",
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊  الإحصائيات",           callback_data="admin_stats")],
        [
            InlineKeyboardButton("📦  تصدير قاعدة البيانات", callback_data="admin_export"),
            InlineKeyboardButton("🔄  إعادة البناء",         callback_data="admin_rebuild"),
        ],
        [
            InlineKeyboardButton("📑  سجل الأخطاء",          callback_data="admin_logs"),
            InlineKeyboardButton("📢  بث للجميع",             callback_data="admin_broadcast"),
        ],
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Welcome / Help
# ═══════════════════════════════════════════════════════════════════════════

def msg_welcome(first_name: str) -> str:
    return (
        "🎙 *Libyan ASR Dataset Builder*\n"
        "══════════════════════════════\n\n"
        f"أهلاً وسهلاً *{first_name}* 👋\n\n"
        "أنا بوت بناء قاعدة البيانات الصوتية الليبية.\n"
        "أرسل أيّ مقطع صوتي وسأتولّى كلّ شيء تلقائياً ✨\n\n"
        "┌─ *كيف يعمل البوت؟*\n"
        "│  ➊  أرسل مقطعاً صوتياً أو ملفاً\n"
        "│  ➋  يُحوَّل تلقائياً إلى WAV نظيف\n"
        "│  ➌  يُنسَخ النص بالذكاء الاصطناعي\n"
        "│  ➍  يُحفَظ في قاعدة البيانات فوراً\n"
        "└──────────────────────────────\n\n"
        "👇 *استخدم الأزرار أدناه للبدء*"
    )


def msg_help() -> str:
    return (
        "❓ *دليل الاستخدام*\n"
        "══════════════════════════════\n\n"
        "🎙 *الصيغ المقبولة*\n"
        "   `OGG  ·  MP3  ·  WAV  ·  M4A  ·  FLAC`\n\n"
        "⏱ *مدة المقطع المسموحة*\n"
        "   من `٠٫٥` ثانية  ─  حتى `٣٠` ثانية\n\n"
        "🔬 *معالجة تلقائية لكل ملف*\n"
        "   ▸ تحويل إلى `16 kHz` أحادي `16‑bit`\n"
        "   ▸ قصّ الصمت من الطرفين\n"
        "   ▸ تطبيع مستوى الصوت\n"
        "   ▸ نسخ النص بنموذج Whisper\n\n"
        "🔁 *الملفات المكررة*\n"
        "   يُكشف عنها بـ SHA-256 وتُتجاهل تلقائياً\n\n"
        "══════════════════════════════\n"
        "💬 للدعم اضغط  *📞 التواصل مع الإدارة*"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Queue
# ═══════════════════════════════════════════════════════════════════════════

def msg_queue_status(waiting: int, active: int) -> str:
    if waiting == 0 and active == 0:
        return (
            "🟢 *الطابور فارغ*\n"
            "══════════════════════════════\n"
            "البوت متفرّغ تماماً وجاهز لاستقبال ملفات جديدة 🎙"
        )
    total = waiting + active
    bar   = progress_bar(active, total, width=12)
    return (
        "⚙️ *حالة الطابور*\n"
        "══════════════════════════════\n"
        f"⚡ قيد المعالجة  `{bar}`\n"
        f"   ├─ يُعالَج الآن : *{active}* ملف\n"
        f"   └─ في الانتظار  : *{waiting}* ملف\n\n"
        f"📊 الإجمالي : *{total}* ملف"
    )


def msg_file_received(filename: str, position: int, active: int) -> str:
    if position == 0:
        pos_line = "🔄 *يُعالَج الآن مباشرةً*"
    elif position == 1:
        pos_line = "📋 موضعك في الطابور: *التالي* 🔜"
    else:
        pos_line = f"📋 موضعك في الطابور: *{position}*"

    active_line = (
        f"\n⚡ يُعالَج حالياً: *{active}* ملف بالتوازي"
        if active > 0 else ""
    )
    return (
        "📥 *تم استلام ملفك*\n"
        "══════════════════════════════\n"
        f"🔖 الملف   : `{filename}`\n"
        f"{pos_line}"
        f"{active_line}\n\n"
        "🔔 _سيصلك إشعار فور اكتمال المعالجة_"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Processing results
# ═══════════════════════════════════════════════════════════════════════════

def msg_accepted(
    wav_filename: str,
    short_text: str,
    duration: float,
    confidence: float,
    total_accepted: int,
) -> str:
    conf_bar = progress_bar(round(confidence * 10), 10, width=10)
    conf_emoji = "🟢" if confidence >= 0.8 else ("🟡" if confidence >= 0.5 else "🔴")
    return (
        "✅ *قُبل الملف وحُفظ*\n"
        "══════════════════════════════\n"
        f"🔖 الملف   : `{wav_filename}`\n"
        f"📝 النص    : _{short_text}_\n"
        f"⏱ المدة   : `{duration:.1f} ث`\n"
        f"{conf_emoji} الدقة   : `{conf_bar}` *{confidence:.0%}*\n"
        "──────────────────────────────\n"
        f"📊 إجمالي المقبولة: *{total_accepted}* ملف ✨"
    )


def msg_rejected(filename: str, reason: str) -> str:
    return (
        "❌ *رُفض الملف*\n"
        "══════════════════════════════\n"
        f"🔖 الملف  : `{filename}`\n"
        f"⚠️ السبب  : {reason}\n\n"
        "_تحقق أن الصوت يحتوي كلاماً واضحاً\n"
        "ومدته بين ٠٫٥ و٣٠ ثانية ثم أعد الإرسال._"
    )


def msg_duplicate(filename: str) -> str:
    return (
        "🔁 *ملف مكرر — تم تجاهله*\n"
        "══════════════════════════════\n"
        f"🔖 الملف  : `{filename}`\n\n"
        "ℹ️ هذا الملف موجود مسبقاً في قاعدة البيانات.\n"
        "_لا داعي لإعادة الإرسال._"
    )


def msg_download_error(filename: str, error: str) -> str:
    return (
        "⚠️ *تعذّر تنزيل الملف*\n"
        "══════════════════════════════\n"
        f"🔖 الملف  : `{filename}`\n"
        f"🔴 الخطأ  : `{error}`\n\n"
        "_يرجى إعادة إرسال الملف مجدداً._"
    )


def msg_unsupported_format(ext: str, supported: list) -> str:
    fmt_list = "  ·  ".join(f.upper() for f in supported)
    return (
        "⛔ *صيغة غير مدعومة*\n"
        "══════════════════════════════\n"
        f"🔖 الصيغة المرسلة : `.{ext}`\n\n"
        "📋 *الصيغ المقبولة:*\n"
        f"`{fmt_list}`"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════════

def msg_stats(stats: dict, waiting: int, active: int) -> str:
    total    = stats.get("total_files", 0)
    accepted = stats.get("accepted_files", 0)
    rejected = stats.get("rejected_files", 0)
    hours    = stats.get("total_duration_hours", 0.0)
    avg_s    = stats.get("average_duration_seconds", 0.0)
    raw      = stats.get("total_size_bytes", 0)

    size_label = _size_str(raw)
    acc_bar = progress_bar(accepted, total) if total else "░" * 12
    rej_bar = progress_bar(rejected, total) if total else "░" * 12

    return (
        "📊 *إحصائيات قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"📁 إجمالي الملفات  : *{total}*\n\n"
        f"✅ مقبولة  `{acc_bar}`\n"
        f"   └ *{accepted}* ملف  ({pct(accepted, total)})\n\n"
        f"❌ مرفوضة  `{rej_bar}`\n"
        f"   └ *{rejected}* ملف  ({pct(rejected, total)})\n\n"
        "══════════════════════════════\n"
        f"⏱ المدة الكلية   : *{hours:.2f}* ساعة\n"
        f"📏 متوسط المدة   : *{avg_s:.1f}* ثانية\n"
        f"💾 الحجم الكلي   : *{size_label}*\n"
        "──────────────────────────────\n"
        f"⚡ قيد المعالجة  : *{active}* ملف\n"
        f"⏳ في الانتظار   : *{waiting}* ملف"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Admin panel
# ═══════════════════════════════════════════════════════════════════════════

def msg_admin_panel() -> str:
    return (
        "⚙️ *لوحة تحكم الإدارة*\n"
        "══════════════════════════════\n\n"
        "اختر الإجراء من الأزرار أدناه:\n\n"
        "📊  *الإحصائيات*  — تقرير شامل عن قاعدة البيانات\n"
        "📦  *التصدير*     — إرسال قاعدة البيانات إلى Saved Messages\n"
        "🔄  *إعادة البناء* — تحديث ملفات CSV / JSON\n"
        "📑  *السجل*       — تنزيل آخر ملف سجل أخطاء\n"
        "📢  *البث*        — إرسال رسالة لجميع المستخدمين"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Export  (single-file → Saved Messages flow)
# ═══════════════════════════════════════════════════════════════════════════

def msg_export_start(accepted: int) -> str:
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"📁 الملفات المقبولة : *{accepted}* ملف صوتي\n\n"
        "⏳ _جارٍ تجهيز الأرشيف…_"
    )


def msg_export_building(total_files: int = 0) -> str:
    hint = f"\n📁 عدد الملفات: *{total_files}*" if total_files else ""
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"🗜 جارٍ ضغط الملفات إلى أرشيف واحد…{hint}\n\n"
        "⏳ _قد تستغرق العملية بضع دقائق_"
    )


def msg_export_uploading_single(size_mb: float, dest: str = "Saved Messages") -> str:
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"📤 جارٍ رفع الأرشيف إلى *{dest}*…\n"
        f"💾 الحجم : *{size_mb:.1f} MB*\n\n"
        "⏳ _يرجى الانتظار — لا تغلق البوت_"
    )


def msg_export_uploading_part(part: int, total: int, size_mb: float, dest: str = "Saved Messages") -> str:
    bar = progress_bar(part - 1, total, width=12)
    return (
        "📦 *تصدير قاعدة البيانات*\n"
        "══════════════════════════════\n"
        f"📤 يُرفع الجزء *{part}* من *{total}* إلى *{dest}*\n"
        f"💾 حجم الجزء : *{size_mb:.1f} MB*\n\n"
        f"`{bar}` {part - 1}/{total}\n"
        "⏳ _جارٍ الرفع…_"
    )


def msg_export_caption_single(size_mb: float, timestamp: str) -> str:
    return (
        "📦 *Libyan ASR Dataset — نسخة احتياطية*\n"
        "──────────────────────────────\n"
        f"📅 التاريخ : `{timestamp}`\n"
        f"💾 الحجم   : *{size_mb:.1f} MB*\n\n"
        "_أرشيف ZIP يحتوي على الصوتيات والبيانات الوصفية_"
    )


def msg_export_caption_part(part: int, total: int, size_mb: float, timestamp: str) -> str:
    return (
        f"📦 *Libyan ASR Dataset — الجزء {part}/{total}*\n"
        "──────────────────────────────\n"
        f"📅 التاريخ : `{timestamp}`\n"
        f"💾 الحجم   : *{size_mb:.1f} MB*\n\n"
        "_لتجميع الأجزاء: احفظها جميعاً ثم فكّ ضغط الجزء الأول_"
    )


def msg_export_done_single(size_mb: float) -> str:
    return (
        "✅ *اكتمل التصدير*\n"
        "══════════════════════════════\n"
        f"📦 تم إرسال الأرشيف (*{size_mb:.1f} MB*) إلى محادثتك الخاصة.\n\n"
        "💡 _ستجد الملف في رسائلك الخاصة مع البوت_"
    )


def msg_export_done_parts(parts: int, total_mb: float) -> str:
    return (
        "✅ *اكتمل التصدير*\n"
        "══════════════════════════════\n"
        f"📦 تم إرسال *{parts}* جزء (إجمالي *{total_mb:.1f} MB*) إلى محادثتك الخاصة.\n\n"
        "📋 *طريقة تجميع الأجزاء:*\n"
        "   رتّب الأجزاء بالترتيب وافتح أول ملف ZIP\n"
        "   يقوم برنامج 7‑Zip أو WinRAR بتجميعها تلقائياً.\n\n"
        "💡 _الأجزاء في رسائلك الخاصة مع البوت_"
    )


def msg_export_error(error: str) -> str:
    return (
        "🔴 *فشل التصدير*\n"
        "══════════════════════════════\n"
        f"⚠️ الخطأ : `{error}`\n\n"
        "_يرجى المحاولة مجدداً أو مراجعة سجل الأخطاء._"
    )


# kept for backward compatibility
def msg_export_part_caption(part: int, total: int, size_mb: float) -> str:
    return msg_export_caption_part(part, total, size_mb, "─")

def msg_export_part_too_large(part: int, total: int, size_mb: float) -> str:
    return f"⚠️ الجزء {part}/{total} ({size_mb:.1f} MB) أكبر من حد تيليجرام — تُخطَّى."


# ═══════════════════════════════════════════════════════════════════════════
# Rebuild
# ═══════════════════════════════════════════════════════════════════════════

def msg_rebuild_start() -> str:
    return (
        "🔄 *إعادة بناء ملفات Dataset*\n"
        "══════════════════════════════\n"
        "⏳ جارٍ إعادة بناء  `metadata.csv`  و  `dataset.json`…"
    )


def msg_rebuild_done(accepted: int) -> str:
    return (
        "✅ *اكتملت إعادة البناء*\n"
        "══════════════════════════════\n"
        f"📁 إجمالي الملفات المقبولة: *{accepted}* ملف\n\n"
        "_تم تحديث جميع ملفات البيانات الوصفية بنجاح_ ✨"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Broadcast
# ═══════════════════════════════════════════════════════════════════════════

def msg_broadcast_guide() -> str:
    return (
        "📢 *بث رسالة للجميع*\n"
        "══════════════════════════════\n"
        "أرسل الأمر مع نص الرسالة:\n\n"
        "`/broadcast نص الرسالة هنا`\n\n"
        "📢 *البث* — إرسال رسالة لجميع المستخدمين"
    )


def msg_broadcast_done(success: int) -> str:
    return (
        "📢 *اكتمل البث*\n"
        "══════════════════════════════\n"
        f"✅ تم الإرسال إلى *{success}* مستخدم بنجاح."
    )


def msg_broadcast_no_users() -> str:
    return (
        "⚠️ *لا يوجد مستخدمون*\n"
        "══════════════════════════════\n"
        "لم يتم العثور على مستخدمين مسجّلين في قاعدة البيانات."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Contact / Logs / Misc
# ═══════════════════════════════════════════════════════════════════════════

def msg_contact() -> str:
    return (
        "📞 *التواصل مع الإدارة*\n"
        "══════════════════════════════\n"
        "للتواصل أو الإبلاغ عن مشكلة:\n"
        "راسلنا على الحساب المخصص للإدارة.\n\n"
        "🕐 _سيتم الرد في أقرب وقت ممكن_"
    )


def msg_no_logs() -> str:
    return (
        "⚠️ *لا توجد سجلات*\n"
        "══════════════════════════════\n"
        "لم يتم العثور على ملفات سجل (Logs) حتى الآن."
    )


def msg_log_caption() -> str:
    return "📑 *أحدث سجل للأخطاء*\n_تم تنزيله من الخادم_ 🖥"


def msg_unauthorized() -> str:
    return "⛔ *غير مصرح*\nهذا الأمر مخصص للإدارة فقط."


# ═══════════════════════════════════════════════════════════════════════════
# Upload retry (used during send_document retries)
# ═══════════════════════════════════════════════════════════════════════════

def msg_upload_retry(attempt: int, total: int, error: str, delay: int) -> str:
    bar = progress_bar(attempt, total, width=8)
    return (
        f"🔁 *إعادة محاولة الرفع*\n"
        f"`{bar}` المحاولة {attempt}/{total}\n"
        f"⚠️ الخطأ  : `{error}`\n"
        f"⏳ الانتظار : {delay} ثانية…"
    )
