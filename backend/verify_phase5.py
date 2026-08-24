# -*- coding: utf-8 -*-
"""تحقق المرحلة 5 — الصوت.

    python backend/verify_phase5.py

يفحص المسار كاملاً بمفاتيح حقيقية: نص → TTS → ffmpeg → ogg/opus → STT،
وقاعدة «صوت داخل ← صوت خارج»، ومرافقة النص والأزرار لكل رد صوتي،
والتعامل مع الفشل بلا إزعاج الزبون (SPEC 9).

إن لم يكن ffmpeg متاحاً يمكن تمرير مساره بـ FFMPEG_BIN. الإنتاج يأخذه
من الصورة مباشرة (Dockerfile).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# للتطوير المحلي فقط: نسخة ffmpeg المعزولة داخل البيئة الافتراضية.
if not os.getenv("FFMPEG_BIN"):
    try:
        import imageio_ffmpeg
        os.environ["FFMPEG_BIN"] = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        pass

import config           # noqa: E402
import platform_adapter  # noqa: E402
import telegram_api     # noqa: E402
import texts            # noqa: E402
import voice            # noqa: E402
from platform_adapter import User  # noqa: E402

ok = True
PHRASE = "مرحبا، بدي احجز طاولة لأربع أشخاص يوم الخميس"


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


def main() -> int:
    print("=" * 62)
    print("تحقق المرحلة 5 — الصوت")
    print("=" * 62)

    # ------------------------------------------------- 1) الجاهزية
    print("\n1) الجاهزية")
    check(voice.available(), "مفتاح ElevenLabs ومعرّف الصوت موجودان")
    check(voice.ffmpeg_ready(), "ffmpeg متاح (%s)" % voice.ffmpeg_bin())

    # ------------------------------------------ 2) اختصار الرد الصوتي
    print("\n2) اختصار الرد الصوتي (SPEC 9 — حد 40 كلمة)")
    long_text = " ".join("كلمة%d" % i for i in range(80))
    short = voice.shorten(long_text)
    check(len(short.split()) <= voice.MAX_VOICE_WORDS + 1,
          "النص الطويل قُصّ إلى %d كلمة" % len(short.split()))
    noisy = "شوف المنيو هون https://example.com/menu 🌿 **مهم** • بند"
    clean = voice.shorten(noisy)
    check("http" not in clean, "الروابط تُحذف قبل النطق")
    check("🌿" not in clean and "*" not in clean,
          "الإيموجي وعلامات التنسيق تُحذف")
    check(voice.shorten("") == "", "نص فارغ يعطي فارغاً")

    # --------------------------------------- 3) نص → صوت → ogg/opus
    print("\n3) نص → TTS → ffmpeg → ogg/opus")
    mp3 = voice.synthesize(PHRASE)
    check(len(mp3) > 1000, "TTS أنتج mp3 (%d بايت)" % len(mp3))
    ogg = voice.to_ogg_opus(mp3)
    check(len(ogg) > 500, "ffmpeg أنتج ogg (%d بايت)" % len(ogg))
    check(ogg[:4] == b"OggS",
          "الصيغة ogg فعلاً — تليجرام يعرضها رسالة صوتية لا مرفقاً")

    # ------------------------------------------- 4) الدورة الكاملة
    print("\n4) الدورة الكاملة: صوت → STT → نص")
    back = voice.transcribe(ogg, filename="reply.ogg")
    print("     المُدخل : %s" % PHRASE)
    print("     المُخرَج: %s" % back)
    check(bool(back), "STT أعاد نصاً")
    words_in = set(PHRASE.replace("،", " ").split())
    words_out = set((back or "").replace("،", " ").split())
    overlap = len(words_in & words_out) / max(1, len(words_in))
    check(overlap >= 0.6, "تطابق الكلمات %.0f%%" % (100 * overlap))

    # ------------------------- 5) صوت داخل ← صوت خارج عبر المحوّل
    print("\n5) صوت داخل ← صوت خارج (SPEC 9)")
    sent = {"voice": 0, "text": 0}

    def fake_send_voice(chat_id, audio, caption=""):
        sent["voice"] += 1
        return {"ok": True}

    def fake_send_message(chat_id, text, reply_markup=None):
        sent["text"] += 1
        return {"ok": True, "result": {"message_id": 1}}

    telegram_api.send_voice = fake_send_voice
    telegram_api.send_message = fake_send_message
    adapter = platform_adapter.TelegramAdapter()

    u_text = User("telegram", "t1", "t1", voice=False)
    adapter.send_buttons(u_text, "أهلاً", [("زر", "H")])
    check(sent["voice"] == 0 and sent["text"] == 1,
          "رسالة نصية ← رد نصي فقط، بلا صوت")

    sent["voice"] = sent["text"] = 0
    u_voice = User("telegram", "t2", "t2", voice=True)
    adapter.send_buttons(u_voice, "أهلاً فيك في عود وناي", [("زر", "H")])
    check(sent["voice"] == 1, "رسالة صوتية ← أُرسل رد صوتي")
    check(sent["text"] == 1,
          "ومعه النص والأزرار دائماً — الأزرار لا تُنقر من الصوت")

    adapter.send_text(u_voice, "رسالة ثانية في نفس النوبة")
    check(sent["voice"] == 1, "لا يتكرّر الصوت في نفس النوبة (%d)"
          % sent["voice"])
    check(sent["text"] == 2, "بينما النص يُرسل لكل رسالة")

    # ------------------------------------------ 6) التعامل مع الفشل
    print("\n6) التعامل مع الفشل بلا إزعاج الزبون (SPEC 9)")
    real_key = config.ELEVENLABS_API_KEY
    try:
        config.ELEVENLABS_API_KEY = "bad-key-for-test"
        check(voice.synthesize("تجربة") == b"",
              "مفتاح خاطئ ← TTS يعيد فارغاً بلا استثناء")
        check(voice.transcribe(ogg) == "",
              "مفتاح خاطئ ← STT يعيد فارغاً بلا استثناء")
        check(voice.render("تجربة") == b"", "render يعيد فارغاً")

        sent["voice"] = sent["text"] = 0
        u3 = User("telegram", "t3", "t3", voice=True)
        adapter.send_buttons(u3, "رسالة", [("زر", "H")])
        check(sent["voice"] == 0 and sent["text"] == 1,
              "عند فشل الصوت يكمل نصاً — الزبون لا يرى خطأ")
    finally:
        config.ELEVENLABS_API_KEY = real_key

    real_bin = os.environ.get("FFMPEG_BIN")
    try:
        os.environ["FFMPEG_BIN"] = "ffmpeg-does-not-exist"
        check(voice.to_ogg_opus(mp3) == b"",
              "ffmpeg مفقود ← تحويل فارغ بلا انهيار")
    finally:
        if real_bin:
            os.environ["FFMPEG_BIN"] = real_bin

    # --------------------------------------- 7) رسالة فشل النسخ
    print("\n7) نص الاعتذار عند تعذّر الفهم")
    for lang in ("ar", "en"):
        msg = texts.t(lang, "voice_failed")
        check(bool(msg) and "{" not in msg, "%s: نص جاهز بلا متغيّرات" % lang)

    print("\n" + "=" * 62)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
