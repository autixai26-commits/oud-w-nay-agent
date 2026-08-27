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
        check(config.RESTAURANT_PHONE not in msg,
              "%s: الاعتذار لا يعطي رقم الهاتف — ليس «معلومة غير متوفرة»"
              % lang)

    extra_checks()
    extra_checks_v2()
    extra_checks_v3()
    extra_checks_v4()

    # المحوّل يحفظ خريطة الأزرار في حالة المستخدم، فيخلّف أثراً
    # للمستخدمين الوهميين. ننظّفه حتى لا يلوّث قاعدة الإنتاج.
    import db as _db
    for _u in ("t1", "t2", "t3"):
        _db.client().table("user_state").delete().eq("user_id", _u).execute()

    print("\n" + "=" * 62)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 62)
    return 0 if ok else 1




# ------------------------------------------------------------------ إضافات
# ولّدها اختبار حقيقي على تليجرام: الأرقام كانت تُنطق مشوّشة.
def extra_checks() -> None:
    print("\n8) نطق الأرقام بالكلمات (SPEC 9)")
    cases = [
        ("سعر التبولة 3.750 د.أ", ["ثلاثة", "دنانير", "سبعمئة"], ["3.750"]),
        ("موعدك الساعة 7:00", ["السابعة"], ["7:00"]),
        ("يوم 30/8", ["ثلاثين", "آب"], ["30/8"]),
        ("خصم 25%", ["خمسة وعشرين", "بالمئة"], ["25%"]),
        ("طاولة 12 لـ4 أشخاص", ["اثنا عشر", "أربعة"], ["12"]),
    ]
    for src, must, must_not in cases:
        out = voice.spoken_numbers(src, "ar")
        good = all(w in out for w in must) and all(w not in out
                                                   for w in must_not)
        check(good, "«%s» ← %s" % (src, out))

    check(voice.spoken_numbers("رمز الحجز 21ME29", "ar").find("21ME29") >= 0,
          "رمز الحجز الأبجدي الرقمي يبقى كما هو")
    check(voice.spoken_numbers("Table 4 at 7:00", "en") == "Table 4 at 7:00",
          "الإنجليزية لا تُحوَّل — تُنطق سليمة أصلاً")
    check(voice.number_words_ar(0) == "صفر"
          and voice.number_words_ar(139) == "مئة وتسعة وثلاثين"
          and voice.number_words_ar(1000) == "ألف",
          "محوّل الأعداد سليم على حالات حدّية")

    print("\n9) التحويل يمر فعلياً قبل محرّك الصوت")
    seen = {}
    real = voice.shorten

    def spy(text):
        seen["text"] = text
        return real(text)

    voice.shorten = spy
    try:
        voice.synthesize("سعر التبولة 3.750 د.أ", "ar")
    finally:
        voice.shorten = real
    check("ثلاثة" in seen.get("text", ""),
          "النص الواصل للتوليد منطوق لا رقمي")




def extra_checks_v2() -> None:
    """الجولة الثانية: تصحيح نطق «أرجيلة» بالقاف الأردنية."""
    print("\n10) تصحيح النطق للهجة الأردنية (SPEC 9)")
    out = voice.fix_pronunciation("عندنا أرجيلة بنكهات متعددة", "ar")
    check(voice.SHISHA_SPOKEN in out and "أرجيلة" not in out,
          "«أرجيلة» ← «%s» — %s" % (voice.SHISHA_SPOKEN, out))
    check(voice.fix_pronunciation("الأرجيلة حلوة", "ar")
          == "ال%s حلوة" % voice.SHISHA_SPOKEN,
          "الصيغة المعرَّفة تُصحَّح أيضاً")
    check(voice.fix_pronunciation("shisha is nice", "en") == "shisha is nice",
          "الإنجليزية لا تُمسّ")

    seen = {}
    real = voice.shorten

    def spy(text):
        seen["text"] = text
        return real(text)

    voice.shorten = spy
    try:
        voice.synthesize("عندنا أرجيلة بـ 8.000 د.أ", "ar")
    finally:
        voice.shorten = real
    body = seen.get("text", "")
    check(voice.SHISHA_SPOKEN in body, "التصحيح يمر فعلياً قبل محرّك الصوت")
    check("تمن" in body, "ومعه تحويل الأرقام في نفس المسار")




def extra_checks_v3() -> None:
    """الجولة الثالثة: تشكيل أسماء المنيو الملتبسة، ونطق الأرجيلة."""
    print("\n11) تشكيل أسماء المنيو الملتبسة (SPEC 9)")
    # «مشكلة» بلا تشكيل تُقرأ problem لا «متنوّعة» — أخطر التباس.
    out = voice.add_tashkeel("مشاوي مشكلة", "ar")
    check(out == "مَشاوي مُشَكَّلة", "«مشاوي مشكلة» ← %s" % out)
    check(voice.add_tashkeel("فواكه مشكلة", "ar").endswith("مُشَكَّلة"),
          "«فواكه مشكلة» تُشكَّل أيضاً")
    check(voice.add_tashkeel("خضار مشكل", "ar") == "خُضار مُشَكَّل",
          "المذكّر «مشكل» يُشكَّل ولا تبتلعه «مشكلة»")
    check(voice.add_tashkeel("سلطة فتوش", "ar").startswith("سَلَطة"),
          "«سلطة» الطعام لا «سُلْطة» الحكم")
    check(voice.add_tashkeel("حمص بيروتي", "ar").startswith("حُمُّص"),
          "«حمص» الحبّ لا «حِمْص» المدينة")
    check(voice.add_tashkeel("كبة نية", "ar").startswith("كُبَّة"), "«كبة»")
    check(voice.add_tashkeel("جوانح مقلية", "ar") == "جْوانِح مَقْلية",
          "«مقلية» لا تبتلعها «مقلي»")
    check(voice.add_tashkeel("Mixed grill", "en") == "Mixed grill",
          "الإنجليزية لا تُمسّ")

    print("\n12) تغطية المنيو: كل اسم يمر بالتشكيل بلا كسر")
    import db as _db
    names = [m["name_ar"] for m in _db.all_menu_items()]
    broken = [n for n in names if not voice.add_tashkeel(n, "ar")]
    check(not broken, "كل الـ%d صنف تمر سليمة" % len(names))
    touched = [n for n in names if voice.add_tashkeel(n, "ar") != n]
    check(len(touched) >= 40,
          "التشكيل يطال %d من %d صنف" % (len(touched), len(names)))

    print("\n13) نطق الأرجيلة")
    check(voice.SHISHA_SPOKEN != "أرجيلة",
          "الصيغة المنطوقة تختلف عن المكتوبة (%s)" % voice.SHISHA_SPOKEN)
    check(voice.fix_pronunciation("الأرجيلة حلوة", "ar")
          == "ال%s حلوة" % voice.SHISHA_SPOKEN,
          "الصيغة المعرَّفة تُعالَج ولا تبتلعها المجرّدة")
    for m in _db.all_menu_items():
        if "أرجيلة" in m["name_ar"]:
            spoken = voice.fix_pronunciation(m["name_ar"], "ar")
            check("أرجيلة" not in spoken,
                  "«%s» ← %s" % (m["name_ar"], spoken))
            break

    print("\n14) ترتيب المعالجة: أرقام ثم نطق ثم تشكيل")
    seen = {}
    real = voice.shorten

    def spy(text):
        seen["text"] = text
        return real(text)

    voice.shorten = spy
    try:
        voice.synthesize("مشاوي مشكلة بـ 8.750 د.أ مع أرجيلة", "ar")
    finally:
        voice.shorten = real
    body = seen.get("text", "")
    check("مُشَكَّلة" in body, "التشكيل مطبَّق")
    check(voice.SHISHA_SPOKEN in body, "تصحيح النطق مطبَّق")
    check("تمن" in body, "تحويل الأرقام مطبَّق")
    check("8.750" not in body and "أرجيلة" not in body,
          "ولا بقايا من الصور الأصلية")




def extra_checks_v4() -> None:
    """الجولة الرابعة: G صلبة، ونصف الدينار، والثمانية الأردنية."""
    print("\n15) صوت G الصلب في «أرجيلة» (مرجع مشروع العيادة)")
    check(voice.SHISHA_SPOKEN == "أرغيلة",
          "تُكتب بالغين — أقرب حرف عربي للـG الصلبة في النطق الآلي")
    check(voice.VOICE_SETTINGS.get("stability") == 0.45
          and voice.VOICE_SETTINGS.get("style") == 0
          and voice.VOICE_SETTINGS.get("use_speaker_boost") is True,
          "إعدادات الصوت ممرَّرة — بدونها يعود المحرّك للجيم الناعمة")
    out = voice.fix_pronunciation("عندنا أرجيلة وأرجيلة عجمي", "ar")
    check("أرجيلة" not in out and out.count("أرغيلة") == 2,
          "كل مواضع الكلمة تُعالَج — %s" % out)

    print("\n16) نصف الدينار يُنطق «ونص» (SPEC 9)")
    for src, want in (("7.500 د.أ", "سبعة ونص"), ("6.500 د.أ", "ستة ونص"),
                      ("2.500 د.أ", "اثنين ونص"), ("10.500 د.أ", "عشرة ونص")):
        got = voice.spoken_numbers(src, "ar")
        check(got == want, "«%s» ← %s" % (src, got))
    # الكسور الأخرى تبقى بالفلوس
    check("فلس" in voice.spoken_numbers("3.750 د.أ", "ar"),
          "والكسور غير النصف تبقى بالفلوس")

    print("\n17) الثمانية باللهجة الأردنية «تمن» (SPEC 9)")
    check(voice.number_words_ar(8) == "تمن", "المفرد: تمن")
    check(voice.number_words_ar(18) == "تمنتعش", "الثامن عشر: تمنتعش")
    check(voice.number_words_ar(80) == "تمانين", "الثمانون: تمانين")
    check(voice.number_words_ar(800) == "تمنمية", "الثمانمئة: تمنمية")
    check("ثماني" not in voice.number_words_ar(888),
          "ولا أثر للفصحى في 888 — %s" % voice.number_words_ar(888))
    check("التامنة" in voice.spoken_numbers("الساعة 8:00", "ar"),
          "والساعة الثامنة: التامنة")
    check("تمن" in voice.spoken_numbers("8.000 د.أ", "ar"),
          "والسعر: %s" % voice.spoken_numbers("8.000 د.أ", "ar"))

    print("\n18) المحرّك يعيد ogg/opus مباشرة")
    check(voice.TTS_OUTPUT_FORMAT == "opus_48000_32",
          "الصيغة المطلوبة هي صيغة تليجرام الرسمية للرسالة الصوتية")
    audio = voice.render("عندنا أرجيلة بسبعة ونص", "ar")
    check(bool(audio) and audio[:4] == b"OggS",
          "الناتج ogg بلا حاجة لتحويل ffmpeg (%d بايت)" % len(audio))


if __name__ == "__main__":
    raise SystemExit(main())
