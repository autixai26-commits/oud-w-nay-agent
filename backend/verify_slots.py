# -*- coding: utf-8 -*-
"""تحقق طبقة الفهم متعدد الحقول — الاستخراج والدمج والتوجيه.

يغطي أربع طبقات مستقلة، كلٌّ منها انكسرت مرة في اختبار حقيقي:
  1. الاستخراج نفسه: هل تُقرأ الحقول من جملة واحدة؟
  2. المجموعة السلبية: هل تبقى الرسائل العادية خارج تدفق الحجز؟
  3. المحادثة كاملة: هل يُسأل عن الناقص فقط لا عن كل شيء؟
  4. اللغة والهاتف وحجز الإجراء الذرّي.

المجموعة السلبية ليست تكميلاً: كل توسيع في الاستخراج يُقاس بما يلتقطه
وبما يجب ألا يلتقطه معاً، وغياب النصف الثاني هو ما سمح بتراجعات سابقة.
"""
import sys
from datetime import timedelta

import booking
import config
import conversation
import db
import platform_adapter
import scheduler
import slots
import texts
from platform_adapter import User

UID = "__verifyslots__"
ok = True
sent: list = []


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class Fake(platform_adapter.BaseAdapter):
    platform = "telegram"

    def send_text(self, user, text):
        sent.append({"text": text, "buttons": [], "nav": [], "link": None})

    def send_buttons(self, user, text, buttons, nav=None):
        platform_adapter._validate(buttons)
        sent.append({"text": text, "buttons": list(buttons),
                     "nav": list(nav or []), "link": None})

    def send_link(self, user, text, label, url):
        sent.append({"text": text, "buttons": [], "nav": [],
                     "link": (label, url)})


def cleanup() -> None:
    c = db.client()
    c.table("booking_sessions").delete().eq("user_id", UID).execute()
    c.table("reservations").delete().eq("user_id", UID).execute()
    c.table("user_state").delete().eq("user_id", UID).execute()


def run(user, lang, steps) -> list:
    out = []
    for step in steps:
        sent.clear()
        if step.startswith("#"):
            conversation.handle_text(user, step[1:], lang)
        else:
            conversation.handle_callback(user, step, lang)
        out.extend(sent)
    return out


def asked(msgs, key) -> bool:
    """هل طُرح السؤال المقابل لهذا المفتاح في أي من الرسائل؟"""
    want = texts.t("ar", key)
    return any(want in (m["text"] or "") for m in msgs)


def main() -> int:                                    # noqa: C901
    print("=" * 66)
    print("تحقق طبقة الفهم متعدد الحقول (slot-filling)")
    print("=" * 66)

    platform_adapter.ADAPTERS["telegram"] = Fake()
    user = User("telegram", UID, UID)
    today = config.today_local()
    tomorrow = today + timedelta(days=1)
    after = today + timedelta(days=2)

    # ------------------------------------------------ 1) الاستخراج
    print("\n1) استخراج الحقول من رسالة واحدة")
    cases = [
        # الحالة الحرفية من تقرير الاختبار
        ("بكرا شخصين الساعة 4",
         {"date": tomorrow.isoformat(), "party": 2, "hour": 16}),
        ("بكرا شخصين الساعه 4",
         {"date": tomorrow.isoformat(), "party": 2, "hour": 16}),
        ("اليوم 4 اشخاص الساعة 8 مساء",
         {"date": today.isoformat(), "party": 4, "hour": 20}),
        ("بعد بكرا الساعة 10 بالليل",
         {"date": after.isoformat(), "hour": 22}),
        ("بدي احجز بكرا لأربعة أشخاص عائلي",
         {"date": tomorrow.isoformat(), "party": 4, "type": "family"}),
        ("شباب 6 اشخاص الساعة 9",
         {"party": 6, "hour": 21, "type": "singles"}),
        ("table for 4 tomorrow at 9",
         {"date": tomorrow.isoformat(), "party": 4, "hour": 21}),
        ("احنا 5 بكرا",
         {"party": 5, "date": tomorrow.isoformat()}),
        ("لحالي اليوم الساعة 7",
         {"party": 1, "date": today.isoformat(), "hour": 19}),
        ("٣ اشخاص بكره الساعه ٨",
         {"party": 3, "date": tomorrow.isoformat(), "hour": 20}),
        ("طاولة لتسعة بكرا", {"party": 9, "date": tomorrow.isoformat()}),
        # «على 7» مرساةُ وقت أردنية شائعة كـ«الساعة 7»
        ("بدي احجز طاولة لعائلة اليوم على 7",
         {"hour": 19, "date": today.isoformat(), "type": "family"}),
        ("اليوم على 9 لأربعة",
         {"hour": 21, "party": 4, "date": today.isoformat()}),
    ]
    for phrase, want in cases:
        got = slots.extract(phrase)
        good = all(got.get(k) == v for k, v in want.items())
        check(good, "«%s» -> %s" % (phrase, got))

    # الساعة تُنتزع قبل العدد، وإلا صارت «4» أربعةَ أشخاص.
    got = slots.extract("بكرا شخصين الساعة 4")
    check(got.get("party") == 2 and got.get("hour") == 16,
          "الساعة لا تُقرأ عدداً ولا العكس (party=%s hour=%s)"
          % (got.get("party"), got.get("hour")))

    # «الاثنين» يوم لا عدد.
    got = slots.extract("بدي احجز يوم الاثنين")
    check("party" not in got, "«الاثنين» يوم لا عددَ أشخاص")

    # ساعة خارج الدوام لا تُملأ بالتخمين.
    check("hour" not in slots.extract("الساعة 9 الصبح"),
          "«9 الصبح» خارج الدوام فلا تُملأ")
    check("hour" not in slots.extract("الساعة 12"),
          "«الساعة 12» قبل الافتتاح فلا تُملأ")

    # «على» حرفٌ كثير الورود، فلا يصير مرساةً إلا أمام رقم لا يتبعه
    # اسمُ أشخاص — وإلا ابتلع العددَ وضاع.
    got = slots.extract("بدي احجز على 4 اشخاص الساعة 9")
    check(got.get("party") == 4 and got.get("hour") == 21,
          "«على 4 اشخاص» عددٌ لا وقت (%s)" % got)
    check(not slots.extract("عندكم خصم على الفاتورة"),
          "«على» بلا رقم لا تلتقط شيئاً")
    check("hour" not in slots.extract("على طول بنوصل"),
          "«على طول» ليست وقتاً")

    # ------------------------------------------------ 2) المجموعة السلبية
    print("\n2) رسائل يجب ألا تفتح تدفق حجز (أقل من حقلين)")
    negative = [
        "شو الجو بكرا", "بتفتحوا بكرا؟", "كيف الحال", "شكراً إلكم",
        "وين مكانكم", "شو عندكم أكل", "عندكم صفحة على السوشال ميديا؟",
        "قديش سعر التبولة", "في موقف سيارات", "عندكم أرجيلة؟",
        "بدي أشوف المنيو", "شو رقمكم", "في واي فاي", "الأكل حلال؟",
        "what is the weather", "do you have instagram",
    ]
    for phrase in negative:
        got = slots.extract(phrase)
        check(slots.count(got) < 2, "«%s» -> %d حقل" % (phrase,
                                                        slots.count(got)))

    # ------------------------------------------- 3) المحادثة: الناقص فقط
    print("\n3) المحادثة تسأل عن الناقص فقط")
    cleanup()
    msgs = run(user, "ar", ["#بكرا شخصين الساعة 4"])
    check(not asked(msgs, "ask_date"), "لم يُعد سؤال التاريخ")
    check(not asked(msgs, "ask_period") and not asked(msgs, "ask_hour"),
          "لم يُعد سؤال الوقت")
    check(not asked(msgs, "ask_party"), "لم يُعد سؤال عدد الأشخاص")
    check(asked(msgs, "ask_booking_type"),
          "سُئل عن نوع الجلسة — الحقل الوحيد الذي لم تحمله الرسالة")

    data = conversation._data(user)
    check(data.get("date") == tomorrow.isoformat()
          and data.get("hour") == 16 and data.get("party") == 2,
          "الحقول الثلاثة محفوظة: %s" % {k: data.get(k)
                                          for k in ("date", "hour", "party")})

    # وبعد النوع يمضي للاسم مباشرة، لا للتاريخ ولا للوقت ولا للعدد.
    msgs = run(user, "ar", ["B:t:family"])
    check(asked(msgs, "ask_name"), "بعد النوع: سؤال الاسم مباشرة")
    check(not asked(msgs, "ask_date") and not asked(msgs, "ask_party"),
          "لم يُطرح أي سؤال سبق أن أجابته الرسالة")

    msgs = run(user, "ar", ["#أسامة"])
    check(asked(msgs, "ask_phone"), "بعد الاسم: سؤال الهاتف")

    # الرقم الذي رُفض في الاختبار الحقيقي
    msgs = run(user, "ar", ["#0793239393"])
    check(not asked(msgs, "invalid_phone"),
          "0793239393 مقبول من أول مرة")
    check(any(m["link"] for m in msgs), "وصل رابط اختيار الطاولة")

    # ------------------------------------------ 4) تعديل حقل واحد
    print("\n4) تعديل حقل واحد لا يصفّر الباقي")
    cleanup()
    run(user, "ar", ["#بكرا 4 اشخاص الساعة 5", "B:t:family"])
    before = dict(conversation._data(user))
    msgs = run(user, "ar", ["#خليها الساعة 8"])
    after_data = conversation._data(user)
    check(after_data.get("hour") == 20, "الساعة تحدّثت إلى 8 مساءً")
    check(after_data.get("date") == before.get("date"), "التاريخ لم يتغيّر")
    check(after_data.get("party") == before.get("party"), "العدد لم يتغيّر")
    check(after_data.get("type") == before.get("type"), "النوع لم يتغيّر")
    check(not asked(msgs, "ask_date") and not asked(msgs, "ask_party"),
          "لم يُعد أي سؤال بسبب تغيير الساعة")

    # التصحيح وسط سؤال الاسم لا يُسجَّل اسماً
    msgs = run(user, "ar", ["#لا خليها 6 اشخاص"])
    check(conversation._data(user).get("party") == 6,
          "«6 اشخاص» جواباً عن سؤال الاسم عُوملت تصحيحاً")
    check(conversation._data(user).get("name") != "لا خليها 6 اشخاص",
          "ولم تُسجَّل اسماً")

    # ------------------------------------------------- 5) اللغة
    print("\n5) لغة الرد تتبع آخر رسالة")
    check(texts.language_signal("بكرا") == "ar", "«بكرا» -> ar")
    check(texts.language_signal("tomorrow at 8") == "en",
          "«tomorrow at 8» -> en")
    check(texts.language_signal("0793239393") is None,
          "رقم بلا حروف لا يبدّل اللغة")
    check(texts.language_signal("ok") == "en", "كلمة قصيرة إنجليزية -> en")
    check(texts.language_signal("مرحبا") == "ar", "كلمة قصيرة عربية -> ar")

    cleanup()
    run(user, "ar", ["#do you have parking"])
    check(db.get_language("telegram", UID) == "en", "تحوّلت إلى الإنجليزية")
    run(user, "en", ["#بكرا"])
    check(db.get_language("telegram", UID) == "ar",
          "رسالة عربية من كلمة واحدة تعيدها للعربية")

    # ------------------------------------------------ 6) الهاتف
    print("\n6) قراءة رقم الهاتف")
    for raw, want in [
            ("0793239393", "0793239393"),
            ("٠٧٩٣٢٣٩٣٩٣", "0793239393"),
            ("079 323 9393", "0793239393"),
            ("صفر سبعة تسعة ثلاثة اثنين ثلاثة تسعة ثلاثة تسعة ثلاثة",
             "0793239393")]:
        got = slots.phone_digits(raw)
        check(got == want, "«%s» -> %s" % (raw, got))
    check(len(slots.phone_digits("07932")) < 9,
          "رقم ناقص يبقى مرفوضاً")

    # --------------------------------------- 7) حجز الإجراء ذرّياً
    print("\n7) لا تذكير مرتين لنفس الحجز")
    cleanup()
    when = config.now_utc() + timedelta(hours=3)
    row = db.client().table("reservations").insert({
        "code": "SLOT01", "platform": "telegram", "user_id": UID,
        "customer_name": "فحص", "customer_phone": "0790000000",
        "party_size": 2, "booking_type": "family",
        "reservation_date": config.to_local(when).date().isoformat(),
        "reservation_at": when.isoformat(), "status": "confirmed",
    }).execute().data[0]

    stamp = config.now_utc().isoformat()
    first = db.claim_reservation(row["id"], "reminder_sent_at", stamp)
    second = db.claim_reservation(row["id"], "reminder_sent_at", stamp)
    check(first, "الدورة الأولى ظفرت بالحجز")
    check(not second, "الدورة الثانية لم تظفر به — لا إرسال مكرر")

    check(db.claim_status(row["id"], "confirmed", "no_show"),
          "نقل الحالة نجح مرة")
    check(not db.claim_status(row["id"], "confirmed", "no_show"),
          "ولم ينجح مرتين")

    # وأن الجدولة نفسها لا ترسل شيئاً بعد أن حُجز الإجراء
    db.update_reservation(row["id"], status="confirmed",
                          reminder_sent_at=None,
                          reservation_at=(
                              config.now_utc()
                              + config.minutes(config.REMINDER_BEFORE_MIN - 1)
                          ).isoformat())
    sent.clear()
    first_tick = scheduler.tick()
    sent_after_first = len(sent)
    sent.clear()
    second_tick = scheduler.tick()
    check(first_tick["reminder"] == 1 and sent_after_first >= 1,
          "الدورة الأولى أرسلت التذكير")
    check(second_tick["reminder"] == 0 and not sent,
          "الدورة الثانية لم ترسل شيئاً")

    # ------------------------------ 8) الحالة المعلّقة تُقيَّم لا تُفرض
    print("\n8) الحالة المعلّقة تُقيَّم عند كل رسالة")

    # قرار التقييم وحده، قبل المحادثة كاملة
    for state, phrase, want, why in [
            (conversation.ST_PHONE, "Hi i wanna book a table", True,
             "تحية + طلب صريح وسط انتظار الهاتف"),
            (conversation.ST_PHONE, "بدي احجز طاولة", True,
             "طلب حجز صريح وسط انتظار الهاتف"),
            (conversation.ST_PHONE, "0793239393", False, "رقم سليم يكمل"),
            (conversation.ST_PHONE, "٠٧٩٣٢٣٩٣٩٣", False, "رقم عربي يكمل"),
            (conversation.ST_PHONE, "07932", False,
             "رقم ناقص خطأ إدخال لا طلب جديد"),
            (conversation.ST_PHONE, "خليها الساعة 8", False,
             "تصحيح حقل لا طلب جديد"),
            (conversation.ST_NAME, "أسامة", False, "اسم عادي يكمل"),
            (conversation.ST_NAME, "خليها الساعة 8", False,
             "تصحيح وسط سؤال الاسم يبقى تصحيحاً"),
            (conversation.ST_NAME, "بدي احجز بكرا", True,
             "طلب صريح لا يُسجَّل اسماً"),
            (conversation.ST_LG_OCCASION, "عيد ميلاد", False,
             "مناسبة عادية تكمل"),
            ("bk_date", "بدي احجز يوم ثاني", False,
             "نقل داخل تدفق قائم لا إلغاء له"),
            ("bk_date", "Hi i wanna book a table", True,
             "تحية مع طلب تُنهي حتى حالة أزرار")]:
        got = conversation._starts_over(state, phrase)
        check(got == want, "[%s] «%s» -> %s (%s)"
              % (state, phrase, "طلب جديد" if got else "استمرار", why))

    check(slots.is_greeting("مهلا شوي") is False,
          "«مهلا» ليست «هلا» — الحدود لا التضمين")
    check(slots.is_greeting("this is fine") is False,
          "«this» ليست «hi»")

    # المحادثة كاملة: الحالة الحرفية من الصورة
    print("\n   المحادثة العالقة كما في الصورة")
    cleanup()
    run(user, "ar", ["#بكرا 4 اشخاص الساعة 5", "B:t:family", "#أسامة"])
    check(conversation._state(user).get("state") == conversation.ST_PHONE,
          "المحادثة عالقة بانتظار رقم الهاتف")

    # main.py يقرأ اللغة المحفوظة ويمرّرها، فنحاكي ذلك لا نفترض الجديدة.
    msgs = run(user, db.get_language("telegram", UID),
               ["#Hi i wanna book a table"])
    check(not asked(msgs, "invalid_phone"),
          "لم يردّ «الرقم مش واضح» على رسالة استهلالية")
    check(any(texts.t("en", "ask_booking_type") in (m["text"] or "")
              for m in msgs),
          "بدأ تدفق حجز جديد نظيف")
    fresh_data = conversation._data(user)
    check(not fresh_data.get("date") and not fresh_data.get("party"),
          "بلا بقايا من التدفق القديم: %s"
          % {k: v for k, v in fresh_data.items() if not k.startswith("_")})
    check(db.get_language("telegram", UID) == "en",
          "وردّ بالإنجليزية كلغة الرسالة")

    # وبالعربية كذلك
    cleanup()
    run(user, "ar", ["#بكرا 4 اشخاص الساعة 5", "B:t:family", "#أسامة"])
    msgs = run(user, "ar", ["#بدي احجز طاولة"])
    check(not asked(msgs, "invalid_phone") and asked(msgs,
                                                     "ask_booking_type"),
          "«بدي احجز طاولة» وسط انتظار الهاتف تبدأ تدفقاً جديداً")

    # وأن التعديل وسط التدفق لم ينكسر بهذا كله
    cleanup()
    run(user, "ar", ["#بكرا 4 اشخاص الساعة 5", "B:t:family"])
    kept = dict(conversation._data(user))
    run(user, "ar", ["#خليها الساعة 8"])
    now_data = conversation._data(user)
    check(now_data.get("hour") == 20
          and now_data.get("date") == kept.get("date")
          and now_data.get("party") == kept.get("party"),
          "«خليها الساعة 8» لا تزال تعديلاً لحقل واحد")

    # ورقم ناقص يبقى خطأ إدخال لا طلباً جديداً
    cleanup()
    run(user, "ar", ["#بكرا 4 اشخاص الساعة 5", "B:t:family", "#أسامة"])
    msgs = run(user, "ar", ["#07932"])
    check(asked(msgs, "invalid_phone"), "رقم ناقص يبقى خطأ إدخال")
    check(conversation._state(user).get("state") == conversation.ST_PHONE,
          "والحالة تبقى بانتظار الهاتف")

    cleanup()
    print("\n" + "=" * 66)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 66)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
