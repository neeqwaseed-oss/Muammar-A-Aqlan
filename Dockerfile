FROM python:3.11-slim

# تثبيت الحزم الأساسية ومكتبة الصوت (FFmpeg)
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# تحديد مسار العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات البوت
COPY . .

# أمر التشغيل
CMD ["python", "main.py"]