# 🎙 Libyan ASR Dataset Builder Bot

بوت Telegram لبناء قاعدة بيانات صوتية احترافية جاهزة لتدريب نماذج التعرف على الكلام (ASR).

---

## ⚡ التشغيل السريع

### 1. المتطلبات

| المتطلب | الرابط |
|---------|--------|
| Python 3.10+ | https://www.python.org |
| ffmpeg | https://ffmpeg.org/download.html |
| توكن بوت Telegram | @BotFather على Telegram |

> **ملاحظة:** بعد تثبيت ffmpeg، يجب إضافة مجلد `ffmpeg/bin` إلى متغير البيئة PATH.

---

### 2. الإعداد

```bash
# تشغيل سكريبت الإعداد (Windows)
setup.bat
```

أو يدوياً:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

### 3. الإعدادات

افتح الملف `config/config.yaml` وعدّل:

```yaml
telegram:
  token: "YOUR_BOT_TOKEN_HERE"   # ← ضع توكنك هنا
```

---

### 4. التشغيل

```bash
start.bat
```

أو:

```bash
venv\Scripts\activate
python main.py
```

---

## 📂 هيكل المشروع

```
libyan_asr_bot/
├── main.py                    ← نقطة الدخول الرئيسية
├── requirements.txt
├── setup.bat                  ← إعداد Windows
├── start.bat                  ← تشغيل البوت
│
├── config/
│   ├── config.yaml            ← جميع الإعدادات القابلة للتعديل
│   └── settings.py            ← تحميل الإعدادات (لا تعدّله)
│
├── bot/
│   ├── bot.py                 ← تسجيل البوت والهاندلرز
│   ├── handlers.py            ← منطق المعالجة الكاملة
│   └── queue_manager.py       ← طابور المعالجة المتسلسل
│
├── core/
│   ├── audio/
│   │   └── processor.py       ← تحويل ومعالجة الصوت
│   ├── speech/
│   │   └── transcriber.py     ← تحويل الكلام إلى نص (Faster-Whisper)
│   ├── database/
│   │   └── db_manager.py      ← إدارة قاعدة البيانات SQLite
│   ├── dataset/
│   │   └── dataset_manager.py ← إنشاء وتحديث ملفات Dataset
│   └── exports/
│       └── exporter.py        ← تصدير ZIP
│
├── utils/
│   ├── logger.py              ← نظام السجلات
│   └── file_utils.py          ← أدوات الملفات
│
└── logs/                      ← سجلات التشغيل (تُنشأ تلقائياً)
```

---

## 🗂 هيكل Dataset الناتج

```
Libyan_ASR_Dataset/           ← يُنشأ تلقائياً
├── audio/
│   ├── original/             ← الملفات المقبولة (audio_000001.wav …)
│   └── rejected/             ← الملفات المرفوضة
├── metadata.csv              ← بيانات وصفية كاملة
├── dataset.json              ← صيغة HuggingFace
├── database.sqlite           ← قاعدة البيانات الرئيسية
├── train.csv                 ← 80% تدريب
├── validation.csv            ← 10% تحقق
├── test.csv                  ← 10% اختبار
├── statistics.json           ← إحصائيات
└── README.txt
```

---

## 🤖 أوامر البوت

| الأمر | الوظيفة |
|-------|---------|
| `/start` | لوحة التحكم والترحيب |
| `/stats` | إحصائيات قاعدة البيانات |
| `/export` | تصدير Dataset كاملاً (ZIP) |
| `/rebuild` | إعادة بناء ملفات Dataset من قاعدة البيانات |

---

## ⚙️ الإعدادات الرئيسية (`config/config.yaml`)

| الإعداد | الوصف | القيمة الافتراضية |
|---------|--------|-------------------|
| `audio.min_duration_seconds` | الحد الأدنى لمدة التسجيل | 1.0 ثانية |
| `audio.max_duration_seconds` | الحد الأقصى للتسجيل | 30 ثانية |
| `transcription.model_size` | حجم نموذج Whisper | `large-v2` |
| `transcription.min_confidence` | الحد الأدنى لنسبة الثقة | 0.6 |
| `transcription.language` | اللغة | `ar` |
| `splits.train` | نسبة التدريب | 0.80 |

---

## 🔄 خط المعالجة (Pipeline)

```
استلام ملف صوتي
      ↓
تنزيل من Telegram
      ↓
فحص التكرار (SHA-256)
      ↓
تحويل إلى WAV (16kHz, Mono, PCM 16-bit)
      ↓
قص الصمت + Normalization
      ↓
فحص وجود كلام (VAD)
      ↓
تحويل الكلام إلى نص (Faster-Whisper)
      ↓
فحص الثقة والجودة
      ↓
حفظ الملف + تحديث قاعدة البيانات
      ↓
تحديث جميع ملفات Dataset
      ↓
إشعار المستخدم
```

---

## 🚀 نماذج ASR المدعومة

الـ Dataset الناتج متوافق مع:

- **OpenAI Whisper / Faster-Whisper**
- **Facebook Wav2Vec2**
- **HuBERT**
- **NVIDIA NeMo**
- **HuggingFace Speech Models**

---

## 🔧 استكشاف الأخطاء

**الخطأ: `ffmpeg not found`**
```
تأكد من تثبيت ffmpeg وإضافته إلى PATH
```

**البوت لا يستجيب**
```
تحقق من صحة التوكن في config/config.yaml
```

**بطء في التحويل إلى نص**
```
استخدم نموذجاً أصغر مثل medium أو small في config.yaml
أو قم بتفعيل GPU إذا كان متاحاً
```

**السجلات**
```
logs/bot.log
```

---

## 📈 التطوير المستقبلي

البنية المعيارية تسمح بإضافة:

- واجهة ويب لمراجعة النصوص يدوياً
- دعم لهجات عربية إضافية
- تكامل مع HuggingFace Hub للرفع المباشر
- نظام مراجعة جماعية (Crowdsourcing)
