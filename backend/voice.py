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


def synthesize(text: str, lang: str = "ar") -> bytes:
    """ElevenLabs TTS. يعيد mp3، أو b"" عند أي فشل أو تجاوز حصة."""
    if not available():
        return b""
    # SPEC 9: الأرقام تُنطق بالكلمات، وبعض الكلمات تحتاج صورة نطق
    # أردنية، وإلا خرج الرد مشوّشاً أو بلهجة غريبة.
    body = shorten(fix_pronunciation(spoken_numbers(text, lang), lang))
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


def render(text: str, lang: str = "ar") -> bytes:
    """نص → رسالة صوتية جاهزة للإرسال. b"" يعني: أكمل نصاً فقط."""
    mp3 = synthesize(text, lang)
    if not mp3:
        return b""
    return to_ogg_opus(mp3)


# ------------------------------------------- نطق الأرقام (SPEC 9)
# محرّك الصوت ينطق "3.750" و"7:00" و"30/8" حرفاً حرفاً أو مشوّشاً،
# فنحوّلها لكلمات منطوقة قبل الإرسال.

_ONES = ("صفر", "واحد", "اثنين", "ثلاثة", "أربعة", "خمسة", "ستة",
         "سبعة", "ثمانية", "تسعة", "عشرة", "أحد عشر", "اثنا عشر",
         "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر",
         "ثمانية عشر", "تسعة عشر")
_TENS = {2: "عشرين", 3: "ثلاثين", 4: "أربعين", 5: "خمسين", 6: "ستين",
         7: "سبعين", 8: "ثمانين", 9: "تسعين"}
_HUNDREDS = {1: "مئة", 2: "مئتين", 3: "ثلاثمئة", 4: "أربعمئة", 5: "خمسمئة",
             6: "ستمئة", 7: "سبعمئة", 8: "ثمانمئة", 9: "تسعمئة"}
# الساعات تُنطق بصيغة الترتيب لا العدد: "السابعة" لا "سبعة".
_HOURS = ("", "الواحدة", "الثانية", "الثالثة", "الرابعة", "الخامسة",
          "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة",
          "الحادية عشرة", "الثانية عشرة")
_MONTHS = ("", "كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
           "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني",
           "كانون الأول")
_ORDINAL_DAY = {1: "الأول", 2: "الثاني", 3: "الثالث"}


def number_words_ar(n: int) -> str:
    """يحوّل عدداً صحيحاً (0–9999) إلى كلمات عربية منطوقة."""
    n = int(n)
    if n < 0:
        return "ناقص " + number_words_ar(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] if not ones else "%s و%s" % (_ONES[ones], _TENS[tens])
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = _HUNDREDS[hundreds]
        return head if not rest else "%s و%s" % (head, number_words_ar(rest))
    thousands, rest = divmod(n, 1000)
    if thousands == 1:
        head = "ألف"
    elif thousands == 2:
        head = "ألفين"
    else:
        head = "%s آلاف" % _ONES[thousands]
    return head if not rest else "%s و%s" % (head, number_words_ar(rest))


def _price_ar(match) -> str:
    dinars, fils = int(match.group(1)), int(match.group(2))
    head = "دينار" if dinars == 1 else ("دينارين" if dinars == 2
                                        else "%s دنانير" % number_words_ar(dinars))
    out = head
    if fils:
        out += " و%s فلس" % number_words_ar(fils)
    return out


def _time_ar(match) -> str:
    hour, minute = int(match.group(1)), int(match.group(2))
    label = _HOURS[hour] if 1 <= hour <= 12 else number_words_ar(hour)
    return label if minute == 0 else "%s و%s دقيقة" % (label,
                                                        number_words_ar(minute))


def _date_ar(match) -> str:
    day, month = int(match.group(1)), int(match.group(2))
    d = _ORDINAL_DAY.get(day) or number_words_ar(day)
    m = _MONTHS[month] if 1 <= month <= 12 else number_words_ar(month)
    return "%s من %s" % (d, m)


def spoken_numbers(text: str, lang: str = "ar") -> str:
    """يستبدل الأرقام بصيغتها المنطوقة. العربية فقط — الإنجليزية تُنطق سليمة."""
    if lang != "ar" or not text:
        return text or ""
    out = text
    # الترتيب مهم: السعر ثم الوقت ثم التاريخ ثم الأرقام المجرّدة.
    out = re.sub(r"(\d+)\.(\d{3})\s*(?:د\.أ|دينار|JOD)?", _price_ar, out)
    out = re.sub(r"(?<![0-9])(\d{1,2}):(\d{2})(?![0-9])", _time_ar, out)
    out = re.sub(r"(?<![0-9])(\d{1,2})/(\d{1,2})(?![0-9])", _date_ar, out)
    out = re.sub(r"(\d+)\s*%", lambda m: number_words_ar(m.group(1)) + " بالمئة", out)
    # الجار المانع هو الأرقام والحروف اللاتينية وحدها: الحروف العربية
    # والتطويل لا تمنع التحويل ("لـ4" تُنطق)، بينما "21ME29" يبقى رمزاً.
    out = re.sub(r"(?<![0-9A-Za-z])\d{1,4}(?![0-9A-Za-z])",
                 lambda m: number_words_ar(m.group(0)), out)
    return out


# ------------------------------------------- تصحيح النطق (SPEC 9)
# محرّك الصوت يقرأ بعض الكلمات بلهجة غير أردنية. نكتب له الصورة التي
# تُنطق صحيحاً بالأردنية، فيبقى النص المعروض للزبون كما هو.
PRONUNCIATION_AR = {
    # الجيم القاهرية في «أرجيلة» غريبة عن اللهجة — القاف الأردنية أصح.
    "أرجيلة": "أرقيلة",
    "ارجيلة": "ارقيلة",
    "الأرجيلة": "الأرقيلة",
    "الارجيلة": "الارقيلة",
    "أرجيله": "أرقيلة",
}


def fix_pronunciation(text: str, lang: str = "ar") -> str:
    if lang != "ar" or not text:
        return text or ""
    out = text
    for wrong, right in PRONUNCIATION_AR.items():
        out = out.replace(wrong, right)
    return out
