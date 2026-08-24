# صورة بايثون خفيفة
FROM python:3.11-slim

# ffmpeg ضروري لتحويل صوت ElevenLabs من mp3 لـ ogg/opus
# عشان تيليجرام يعرضها كرسالة صوتية حقيقية مش كملف مرفق.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ المتطلبات لحالها أول عشان طبقة الكاش تضل صالحة
# لما نغيّر الكود بدون ما نغيّر المتطلبات.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render بيمرّر رقم المنفذ بمتغيّر PORT.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
