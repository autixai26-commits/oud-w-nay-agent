# -*- coding: utf-8 -*-
"""تحقق المرحلة 2 — يمشي شجرة الأزرار كاملة باللغتين بلا إرسال شيء لتليجرام.

    python backend/verify_phase2.py

يفحص:
  1. كل مستوى أزرار ≤ 10 خيارات (SPEC 7.1 و 11).
  2. المنيو يعمل بالعربية والإنجليزية، وكل صنف يظهر مرة واحدة.
  3. كل رسالة فيها سعر يرافقها التنويه الضريبي (SPEC 7.4).
  4. قاعدة الكحول ترد بالصيغة الحرفية بلا نداء النموذج (SPEC 7.3).
  5. لا نص موجّه للزبون مكتوب داخل منطق الكود (SPEC 8).
يخرج بالرمز 1 عند أي فشل.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai
import conversation
import db
import platform_adapter
import texts
from platform_adapter import MAX_OPTIONS_PER_LEVEL, User

ok = True
sent: list = []


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class FakeAdapter(platform_adapter.BaseAdapter):
    """يسجّل الرسائل بدل إرسالها، ويطبّق نفس فحص الحدود."""
    platform = "telegram"

    def send_text(self, user, text):
        sent.append({"text": text, "buttons": [], "nav": []})

    def send_buttons(self, user, text, buttons, nav=None):
        platform_adapter._validate(buttons)
        sent.append({"text": text, "buttons": list(buttons),
                     "nav": list(nav or [])})

    def send_link(self, user, text, label, url):
        sent.append({"text": text, "buttons": [], "nav": [],
                     "link": (label, url)})


def walk(lang: str) -> dict:
    """يزور كل callback_data قابل للوصول انطلاقاً من القائمة الرئيسية."""
    user = User("telegram", "verify", "verify")
    seen, queue, screens = set(), ["H"], []
    while queue:
        data = queue.pop(0)
        if data in seen:
            continue
        seen.add(data)
        sent.clear()
        conversation.handle_callback(user, data, lang)
        for msg in sent:
            screens.append({"data": data, **msg})
            for _, target in msg["buttons"] + msg["nav"]:
                if target not in seen:
                    queue.append(target)
    return {"visited": seen, "screens": screens}


def main() -> int:
    print("=" * 56)
    print("تحقق المرحلة 2 — البوت والمنيو")
    print("=" * 56)

    # نستبدل محوّل تليجرام بالوهمي حتى لا يُرسَل شيء فعلياً.
    platform_adapter.ADAPTERS["telegram"] = FakeAdapter()

    menu_items = db.all_menu_items()
    results = {}

    for lang in ("ar", "en"):
        print("\n--- اللغة: %s ---" % lang)
        res = walk(lang)
        results[lang] = res
        print("  شاشات زُرِرت: %d   رسائل: %d"
              % (len(res["visited"]), len(res["screens"])))

        # 1) حد الخيارات
        worst = max((len(s["buttons"]) for s in res["screens"]), default=0)
        check(worst <= MAX_OPTIONS_PER_LEVEL,
              "أقصى عدد خيارات في مستوى واحد: %d (الحد %d)"
              % (worst, MAX_OPTIONS_PER_LEVEL))
        worst_nav = max((len(s["nav"]) for s in res["screens"]), default=0)
        check(worst_nav <= platform_adapter.MAX_QUICK_BUTTONS,
              "أقصى عدد أزرار تنقّل في رسالة: %d (الحد %d)"
              % (worst_nav, platform_adapter.MAX_QUICK_BUTTONS))

        # 2) كل صنف يظهر مرة واحدة على الأقل
        blob = "\n".join(s["text"] for s in res["screens"])
        key = "name_ar" if lang == "ar" else "name_en"
        missing = [m[key] for m in menu_items if m[key] not in blob]
        check(not missing, "كل الـ%d صنف ظاهرة في التصفّح%s"
              % (len(menu_items),
                 "" if not missing else " — ناقص: %s" % missing[:5]))

        # 3) التنويه الضريبي مع كل سعر
        note = texts.t(lang, "tax_note")
        priced = [s for s in res["screens"]
                  if re.search(r"\d+\.\d{3}", s["text"])]
        no_note = [s["data"] for s in priced if note not in s["text"]]
        check(not no_note, "التنويه الضريبي مرافق لكل %d شاشة فيها أسعار%s"
              % (len(priced), "" if not no_note else " — ناقص في %s" % no_note[:3]))

    # 4) قاعدة الكحول
    print("\n--- قاعدة الكحول (SPEC 7.3) ---")
    probes_ar = ["في عندكم بيرة؟", "بتقدموا نبيذ", "عندكم عرق ولا ويسكي"]
    probes_en = ["do you serve wine", "any beer?", "vodka please"]
    for lang, probes in (("ar", probes_ar), ("en", probes_en)):
        expected = texts.t(lang, "alcohol")
        bad = [p for p in probes if ai.reply_to(p, lang) != expected]
        check(not bad, "%s: كل %d سؤال ردّه الصيغة الحرفية%s"
              % (lang, len(probes), "" if not bad else " — فشل: %s" % bad))
    blob_all = "\n".join(s["text"] for s in results["ar"]["screens"])
    leaked = [w for w in ("بيرة", "نبيذ", "ويسكي", "عرق", "فودكا")
              if w in blob_all]
    check(not leaked, "لا ذكر للكحول في أي شاشة تصفّح%s"
          % ("" if not leaked else " — وُجد: %s" % leaked))

    # 5) لا نصوص داخل منطق الكود
    print("\n--- فصل النصوص (SPEC 8) ---")
    arabic = re.compile(r"[؀-ۿ]")
    # رسائل اللوغ والاستثناءات الداخلية ليست نصاً موجّهاً للزبون،
    # فهي لا تصل تليجرام أصلاً. القاعدة تخص ما يقرأه الزبون فقط.
    internal = re.compile(r"\blog\.|\braise\b|logging\.|format=")
    offenders = []
    for name in ("conversation.py", "main.py", "platform_adapter.py"):
        src = (Path(__file__).resolve().parent / name).read_text(encoding="utf-8")
        src = re.sub(r'"""[\s\S]*?"""', "", src)   # إزالة الـdocstrings
        depth = 0                                   # عمق الأقواس داخل نداء داخلي
        for raw in src.split("\n"):
            line = re.sub(r"#.*", "", raw)          # إزالة التعليقات
            skip = depth > 0 or bool(internal.search(line))
            if skip:
                depth += line.count("(") - line.count(")")
                depth = max(0, depth)
                continue
            for m in re.finditer(r'"([^"\n]*)"', line):
                lit = m.group(1)
                # حرف أو حرفان ليسا رسالة للزبون — مثل حدّي نطاق الأرقام
                # العربية عند تحويل الإدخال.
                if len(lit) > 2 and arabic.search(lit):
                    offenders.append("%s: %s" % (name, lit[:40]))
    check(not offenders, "لا نص عربي موجّه للزبون داخل منطق الكود%s"
          % ("" if not offenders else " — %s" % offenders[:3]))

    # ملخص الصفحات
    print("\n--- صفحات المنيو ---")
    for cat in conversation._tree().values():
        for sub in cat["subs"].values():
            n = len(sub["items"])
            pages = max(1, -(-n // conversation.PAGE_SIZE))
            print("    %-14s %3d صنف -> %d صفحة" % (sub["slug"], n, pages))

    extra_checks()
    extra_checks_v2()

    # المسح يمر بتدفق الحجز فيكتب حالة للمستخدم الوهمي — ننظّفها.
    db.client().table("user_state").delete().eq("user_id", "verify").execute()

    print("\n" + "=" * 56)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 56)
    return 0 if ok else 1




# ------------------------------------------------------------------ إضافات
# حالات ولّدها اختبار حقيقي على تليجرام — تُبقى لتمنع رجوع نفس الخلل.
def extra_checks() -> None:
    print("\n--- كشف اللغة تلقائياً (SPEC 8 — شاشة اللغة أُلغيت) ---")
    cases = [("مرحبا بدي احجز", "ar"), ("Hello, a table please", "en"),
             ("شو الدوام", "ar"), ("what time do you close", "en")]
    bad = [t for t, exp in cases if texts.detect_language(t) != exp]
    check(not bad, "اللغة تُكتشف من نص الرسالة%s"
          % ("" if not bad else " — فشل: %s" % bad))

    user = User("telegram", "verify_lang", "verify_lang")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_lang").execute()
    sent.clear()
    conversation.handle_text(user, "Hello, I want to book a table", None)
    blob = "\n".join(s["text"] for s in sent)
    check(texts.AR["choose_language"] not in blob,
          "لا تظهر شاشة اختيار اللغة لمستخدم جديد")
    check(db.get_language("telegram", "verify_lang") == "en",
          "حُفظت اللغة المكتشفة (en)")

    print("\n--- كشف النية قبل الأسئلة الحرة (SPEC 8) ---")
    intents = [("أعطيني رابط جديد", "book"), ("بدي احجز طاولة", "book"),
               ("give me a new link", "book"), ("بدي أعدّل حجزي", "manage"),
               ("بدي ألغي حجزي", "manage"), ("cancel my booking", "manage"),
               ("وين بتقعوا؟", None), ("قديش سعر التبولة", None)]
    wrong = [t for t, exp in intents if ai.detect_intent(t) != exp]
    check(not wrong, "النية تُكتشف صحيحة في %d حالة%s"
          % (len(intents), "" if not wrong else " — فشل: %s" % wrong))

    db.save_user_state("telegram", "verify_lang", language="ar", state="main")
    sent.clear()
    conversation.handle_text(user, "أعطيني رابط جديد", "ar")
    blob = "\n".join(s["text"] for s in sent)
    check(texts.t("ar", "ask_booking_type") in blob,
          "«أعطيني رابط جديد» تبدأ تدفق الحجز لا رد «لا أعرف»")
    check(texts.t("ar", "unknown") not in blob, "ولا تعطي رقم الهاتف")

    sent.clear()
    conversation.handle_text(user, "بدي أعدّل حجزي", "ar")
    blob = "\n".join(s["text"] for s in sent)
    check(texts.t("ar", "unknown") not in blob,
          "«بدي أعدّل حجزي» لا تذهب لمسار «لا أعرف»")

    print("\n--- منع رقم الهاتف في كل جواب (SPEC 8) ---")
    prompt = ai.system_prompt("ar")
    check("Do NOT append the phone number" in prompt,
          "التوجيه صريح في system prompt")

    db.client().table("user_state").delete().eq(
        "user_id", "verify_lang").execute()




def extra_checks_v2() -> None:
    """حالات ولّدتها الجولة الثانية من الاختبار الحقيقي."""
    print("\n--- لا زر لغة إطلاقاً (SPEC 8 المحدّث) ---")
    user = User("telegram", "verify_nolang", "verify_nolang")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_nolang").execute()
    sent.clear()
    conversation.handle_text(user, "مرحبا كيف الحال", None)
    labels = [b[0] for s in sent for b in s["buttons"] + s["nav"]]
    check(texts.AR["btn_switch_lang"] not in labels
          and texts.EN["btn_switch_lang"] not in labels,
          "زر تبديل اللغة غير موجود في أي قائمة")
    actions = [b[1] for s in sent for b in s["buttons"] + s["nav"]]
    check("X" not in actions, "ولا إجراء تبديل لغة معروض")

    print("\n--- تحوّل اللغة تلقائياً عند تغيّرها ---")
    check(db.get_language("telegram", "verify_nolang") == "ar",
          "بدأت بالعربية من أول رسالة")
    sent.clear()
    conversation.handle_text(user, "Do you have a table for four?", "ar")
    check(db.get_language("telegram", "verify_nolang") == "en",
          "تحوّلت للإنجليزية تلقائياً بلا زر")
    sent.clear()
    conversation.handle_text(user, "شو الدوام عندكم", "en")
    check(db.get_language("telegram", "verify_nolang") == "ar",
          "ورجعت للعربية تلقائياً")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_nolang").execute()

    print("\n--- كشف النية من النص المكتوب (صيغ الهمزة والشدّة) ---")
    forms = ["بدي اعدل", "بدي أعدّل", "بدي أعدل حجزي", "بدي الغي",
             "بدي إلغاء", "بدّل حجزي", "بدي أغيّر موعدي"]
    bad = [f for f in forms if ai.detect_intent(f) != "manage"]
    check(not bad, "كل صيغ «تعديل/إلغاء» المكتوبة تُكشف%s"
          % ("" if not bad else " — فشل: %s" % bad))

    u2 = User("telegram", "verify_intent", "verify_intent")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_intent").execute()
    db.save_user_state("telegram", "verify_intent", language="ar",
                       state="main")
    sent.clear()
    conversation.handle_text(u2, "بدي اعدل", "ar")
    blob = "\n".join(s["text"] for s in sent)
    check(texts.t("ar", "unknown") not in blob,
          "«بدي اعدل» المكتوبة لا تذهب لمسار «لا أعرف»")
    check(texts.t("ar", "my_bookings_empty") in blob
          or texts.t("ar", "my_bookings_title") in blob,
          "بل تفتح شاشة حجوزاتي مباشرة")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_intent").execute()

    print("\n--- سياق التعديل لا يُستبدل بحجز جديد ---")
    u3 = User("telegram", "verify_edit", "verify_edit")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_edit").execute()
    db.save_user_state("telegram", "verify_edit", language="ar",
                       state="bk_date",
                       data={"type": "singles", "party": 4,
                             "editing": "ABC123"})
    sent.clear()
    conversation.handle_text(u3, "بدي احجز يوم ثاني", "ar")
    blob = "\n".join(s["text"] for s in sent)
    check(texts.t("ar", "ask_booking_type") not in blob,
          "داخل تدفق نشط لا يُعاد سؤال نوع الحجز")
    check(texts.t("ar", "ask_date") in blob,
          "بل يُعرض اختيار اليوم مباشرة — نقلٌ لا حجز جديد")
    db.client().table("user_state").delete().eq(
        "user_id", "verify_edit").execute()

    print("\n--- صياغة طلب الهاتف ---")
    for lang in ("ar", "en"):
        msg = texts.t(lang, "ask_phone")
        check("🙏" in msg, "%s: الصياغة مهذّبة — %s" % (lang, msg))

    print("\n--- تصحيح المنيو: تفاحتين ---")
    names = [m["name_ar"] for m in db.all_menu_items()]
    check(not any("نفاحتين" in n for n in names),
          "لا وجود لـ«نفاحتين» في قاعدة البيانات")
    check(any("تفاحتين" in n for n in names), "و«تفاحتين» موجودة")


if __name__ == "__main__":
    raise SystemExit(main())
