# -*- coding: utf-8 -*-
"""الرسائل الصوتية — SPEC 9.

المسار الوارد: ogg/opus من تليجرام → ElevenLabs STT → نص → المعالجة العادية.
المسار الصادر: نص → ElevenLabs TTS (mp3) → ffmpeg → ogg/opus → sendVoice.

قاعدة ثابتة: أي فشل في الصوت لا يصل الزبون. يُسجَّل بصمت ويُكمَل نصاً.
"""
import logging
import os
import re
import shutil
import subprocess

import httpx

import config

log = logging.getLogger(__name__)

_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/%s"
_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
_TIMEOUT = httpx.Timeout(90.0, connect=10.0)

# SPEC 9: الرد الصوتي مختصر، والتفاصيل الطويلة تبقى في النص.
MAX_VOICE_WORDS = 40

TTS_MODEL = "eleven_multilingual_v2"


def _headers() -> dict:
    """القيد ٤: هذه الترويسة لا تُطبع ولا تُسجَّل أبداً."""
    return {"xi-api-key": config.ELEVENLABS_API_KEY}


def available() -> bool:
    return bool(config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID)


# --------------------------------------------------------------- ffmpeg
def ffmpeg_bin() -> str:
    """مسار ffmpeg.

    الإنتاج: الحزمة مثبّتة في الصورة (انظر Dockerfile) فيكفي الاسم.
    التطوير المحلي: يمكن تمرير مسار صريح بـ FFMPEG_BIN دون تغيير الكود.
    """
    return os.getenv("FFMPEG_BIN") or "ffmpeg"


def ffmpeg_ready() -> bool:
    binary = ffmpeg_bin()
    return bool(shutil.which(binary) or os.path.isfile(binary))


def to_ogg_opus(mp3: bytes) -> bytes:
    """يحوّل mp3 إلى ogg/opus.

    بدون هذا التحويل يعرض تليجرام الرد كملف مرفق لا كرسالة صوتية.
    يعيد b"" عند أي فشل فيتحوّل النداء إلى رد نصي.
    """
    if not mp3:
        return b""
    try:
        proc = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
             "-f", "ogg", "pipe:1"],
            input=mp3, capture_output=True, timeout=90)
        if proc.returncode != 0 or not proc.stdout:
            log.error("ffmpeg فشل برمز %s", proc.returncode)
            return b""
        return proc.stdout
    except FileNotFoundError:
        log.error("ffmpeg غير موجود — يُرد نصاً فقط")
        return b""
    except Exception as exc:  # noqa: BLE001
        log.error("ffmpeg استثناء: %s", type(exc).__name__)
        return b""


# ------------------------------------------------------ صوت وارد ← نص
def transcribe(audio: bytes, filename: str = "voice.ogg") -> str:
    """ElevenLabs STT. يعيد نصاً فارغاً عند أي فشل."""
    if not audio or not config.ELEVENLABS_API_KEY:
        return ""
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(_STT_URL, headers=_headers(),
                       files={"file": (filename, audio, "audio/ogg")},
                       data={"model_id": config.ELEVENLABS_STT_MODEL})
        if r.status_code != 200:
            log.error("STT رمز الحالة %s", r.status_code)
            return ""
        return (r.json().get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.error("STT استثناء: %s", type(exc).__name__)
        return ""


# ------------------------------------------------------ نص ← صوت صادر
def shorten(text: str) -> str:
    """يقصّ النص لحدود 40 كلمة ويزيل ما لا يُقرأ صوتاً.

    الروابط والإيموجي وعلامات التنسيق تُقرأ بصوت مزعج، والتفاصيل
    الطويلة موجودة أصلاً في الرسالة النصية المرافقة (SPEC 9).
    """
    clean = re.sub(r"https?://\S+", "", text or "")
    clean = re.sub(r"[*_`#•]", " ", clean)
    # نحذف الرموز خارج الحروف والأرقام وعلامات الوقف الأساسية.
    clean = re.sub(r"[^\w\s؀-ۿ.,!?:؛،؟-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    words = clean.split()
    if len(words) <= MAX_VOICE_WORDS:
        return clean
    return " ".join(words[:MAX_VOICE_WORDS]).rstrip(",،.") + "…"


def synthesize(text: str) -> bytes:
    """ElevenLabs TTS. يعيد mp3، أو b"" عند أي فشل أو تجاوز حصة."""
    if not available():
        return b""
    body = shorten(text)
    if not body:
        return b""
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(_TTS_URL % config.ELEVENLABS_VOICE_ID,
                       headers=_headers(),
                       json={"text": body, "model_id": TTS_MODEL})
        if r.status_code != 200:
            # 401 مفتاح، 429 تجاوز حصة — كلاهما يُسجَّل بصمت (SPEC 9).
            log.error("TTS رمز الحالة %s", r.status_code)
            return b""
        return r.content
    except Exception as exc:  # noqa: BLE001
        log.error("TTS استثناء: %s", type(exc).__name__)
        return b""


def render(text: str) -> bytes:
    """نص → رسالة صوتية جاهزة للإرسال. b"" يعني: أكمل نصاً فقط."""
    mp3 = synthesize(text)
    if not mp3:
        return b""
    return to_ogg_opus(mp3)
