# -*- coding: utf-8 -*-
"""تحقق الفصل بين مسار الأدمن ومسار الزبون — SPEC 10.2.

الفحص الحاسم فيه ليس أن الأدمن يُفهم، بل أن **الجملة نفسها بالحرف**
تُعامَل معاملتين مختلفتين حسب مُرسِلها: أمراً إدارياً من الأدمن، ورسالةَ
زبون من غيره. لذلك تُرسَل كل جملة من الطرفين في القسم الرابع.

والاتجاه المعاكس مفحوص كذلك: رسالة زبون عادية من الأدمن نفسه — تصفّح
منيو أو طلب حجز — يجب أن تبقى في مسار الزبون، وإلا لَما استطاع صاحب
المطعم استعمال بوته.
"""
import sys
from datetime import timedelta

import admin
import admin_nlu
import booking
import config
import conversation
import db
import platform_adapter
import texts
from platform_adapter import User

ADMIN_UID = "__verifyadmin__"
GUEST_UID = "__verifyguest__"
ok = True
sent: list = []


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class Fake(platform_adapter.BaseAdapter):
    platform = "telegram"

    def send_text(self, user, text):
        sent.append({"to": user.user_id, "text": text, "buttons": []})

    def send_buttons(self, user, text, buttons, nav=None):
        sent.append({"to": user.user_id, "text": text,
                     "buttons": [b[1] for b in buttons]})

    def send_link(self, user, text, label, url):
        sent.append({"to": user.user_id, "text": text, "buttons": []})


def cleanup() -> None:
    c = db.client()
    for uid in (ADMIN_UID, GUEST_UID):
        c.table("booking_sessions").delete().eq("user_id", uid).execute()
        c.table("reservations").delete().eq("user_id", uid).execute()
        c.table("user_state").delete().eq("user_id", uid).execute()


def say(user, text, lang="ar") -> list:
    sent.clear()
    conversation.handle_text(user, text, lang)
    return list(sent)


def blob(msgs) -> str:
    return " | ".join(m["text"] or "" for m in msgs)


def main() -> int:                                    # noqa: C901
    print("=" * 70)
    print("تحقق فصل مسار الأدمن عن مسار الزبون")
    print("=" * 70)

    platform_adapter.ADAPTERS["telegram"] = Fake()
    boss = User("telegram", ADMIN_UID, ADMIN_UID)
    guest = User("telegram", GUEST_UID, GUEST_UID)
    cleanup()

    c = db.client()
    c.table("admins").delete().eq("user_id", ADMIN_UID).execute()
    c.table("admins").insert({
        "platform": "telegram", "user_id": ADMIN_UID,
        "display_name": "فحص", "is_active": True}).execute()
    check(db.is_admin("telegram", ADMIN_UID), "أدمن الفحص مسجّل")
    check(not db.is_admin("telegram", GUEST_UID), "وزبون الفحص ليس أدمناً")

    # ------------------------------------------- 1) قراءة التعليمة
    print("\n1) قراءة التعليمة الإدارية الحرة")
    for phrase, want in [
            # الرسائل الحرفية الثلاث من محادثة الأدمن
            ("طوله رقم 33 متاحه خلص الزبائن", ("free", ([33], None))),
            ("الطاولة رقم 33 متاحه", ("free", ([33], None))),
            ("عدلها على موقع الحجز", ("clarify_free", ([33], None))),
            # صيغ أخرى
            ("طاولة 5 فضيت", ("free", ([5], None))),
            ("الطاولة 12 راحوا", ("free", ([12], None))),
            ("table 7 is free", ("free", ([7], None))),
            ("الطاولة 33", ("clarify_free", ([33], None))),
            ("الطاولة 12 محجوزة", ("block", ([12], None, None))),
            # فعل الحجز الصريح يحسم الاتجاه: لا غموض بين حجز وتحرير
            ("احجزلي طاولة 20", ("block", ([20], None, None))),
            ("احجز طاولة 5 الساعة 8", ("block", ([5], 20, None))),
            ("ثبت طاولة 9", ("block", ([9], None, None))),
            ("الطاولة 5 محجوزة الساعة 8", ("block", ([5], 20, None))),
            ("table 6 is reserved at 7", ("block", ([6], 19, None))),
            # قائمة طاولات في أمر واحد
            ("بدي تحول طاولة 35 و36 لمتاح", ("free", ([35, 36], None))),
            ("طاولة 35 و36 و37 متاحة", ("free", ([35, 36, 37], None))),
            ("حدث الطاولتين لمتاح طاولة 35 وطاولة36",
             ("free", ([35, 36], None))),
            ("حرر 35 و36", ("free", ([35, 36], None))),
            ("احجز طاولة 5 و6 الساعة 8", ("block", ([5, 6], 20, None))),
            ("شو حجوزات اليوم", ("today", None)),
            ("كم الاشغال اليوم", ("stats", None)),
            ("احجز لأحمد بكرا", ("book", None)),
            ("الغِ الحجز ABC123", ("cancel", "ABC123")),
            ("عدّلها", ("clarify_free", ([33], None))),
    ]:
        got = admin_nlu.understand(phrase, last_table=33)
        check(got == want, "«%s» -> %s" % (phrase, got))

    # ---------------------------- 2) رسائل الزبون لا تُقرأ إدارية
    print("\n2) رسائل زبون عادية: لا إشارة إدارية إطلاقاً")
    for phrase in ["بدي احجز طاولة", "احجزلي طاولة بكرا", "شو المنيو",
                   "وين مكانكم", "عندكم أرجيلة؟", "بدي احجز لحالنا",
                   "كيف الحال", "شو رقمكم", "بكرا شخصين الساعة 4",
                   "I want to book a table", "بدي الغي حجزي"]:
        check(admin_nlu.understand(phrase) is None, "«%s» -> None" % phrase)

    # ------------------------------------ 3) التنفيذ الفعلي بالقاعدة
    print("\n3) التنفيذ الفعلي على قاعدة البيانات")
    cleanup()
    table = next(t for t in db.all_tables() if t["hall"] == "outdoor")
    number = table["table_number"]
    today = config.today_local()
    when = booking.local_datetime(today, 20)
    row = c.table("reservations").insert({
        "code": "ADM001", "platform": "telegram", "user_id": GUEST_UID,
        "customer_name": "ضيف", "customer_phone": "0790000000",
        "party_size": 2, "booking_type": "family", "table_id": table["id"],
        "reservation_date": today.isoformat(),
        "reservation_at": config.to_utc(when).isoformat(),
        "status": "confirmed",
    }).execute().data[0]

    check(table["id"] in db.booked_table_ids(today.isoformat()),
          "الطاولة %d محجوزة قبل التعليمة" % number)

    msgs = say(boss, "الطاولة رقم %d متاحه خلص الزبائن" % number)
    check(texts.t("ar", "admin_table_freed", table=number, date=admin._fmt_day(config.today_local(), "ar")) in blob(msgs),
          "الردّ إداري: تحرّرت الطاولة")
    check(db.get_reservation(row["id"])["status"] == "completed",
          "الحجز صار completed فعلاً في القاعدة")
    check(table["id"] not in db.booked_table_ids(today.isoformat()),
          "والطاولة عادت متاحة — والموقع يقرأ هذا الاستعلام نفسه")
    check("0770800120" not in blob(msgs), "ولا أثر لردّ الزبائن العام")

    # تكرار نفس التعليمة
    msgs = say(boss, "الطاولة رقم %d متاحه" % number)
    check(texts.t("ar", "admin_table_already_free", table=number, date=admin._fmt_day(config.today_local(), "ar"))
          in blob(msgs), "التكرار: متاحة أصلاً — لا ردّ زبون")

    # ------------------------- 4) نفس الجملة من الطرفين تُعامَل مختلفةً
    print("\n4) الجملة نفسها بالحرف من الأدمن ومن الزبون")
    sentence = "الطاولة 33 صارت متاحة"

    cleanup()
    msgs_admin = say(boss, sentence)
    admin_reply = blob(msgs_admin)
    check(bool(msgs_admin), "الأدمن: وصله ردّ")
    check("0770800120" not in admin_reply,
          "الأدمن: لا رقم مطعم في الرد")
    # texts.t يعيد '' للمفتاح المجهول، و'' موجودة في كل نص — فيمرّ الفحص
    # على مفتاح مكتوب خطأً بلا أن يفحص شيئاً. نتثبّت من وجوده أولاً.
    check(bool(texts.t("ar", "my_bookings_empty")),
          "مفتاح «ما عندك حجوزات» موجود فعلاً")
    check(texts.t("ar", "my_bookings_empty") not in admin_reply,
          "الأدمن: لم يُبحث له عن حجوزات شخصية")
    is_admin_reply = (
        texts.t("ar", "admin_table_freed", table=33, date=admin._fmt_day(config.today_local(), "ar")) in admin_reply
        or texts.t("ar", "admin_table_already_free", table=33, date=admin._fmt_day(config.today_local(), "ar")) in admin_reply
        or texts.t("ar", "admin_free_confirm", table=33) in admin_reply
        or texts.t("ar", "admin_table_not_found", table=33) in admin_reply)
    check(is_admin_reply, "الأدمن: الرد إداري — «%s»" % admin_reply[:60])

    msgs_guest = say(guest, sentence)
    guest_reply = blob(msgs_guest)
    check(not any(
        texts.t("ar", k, table=33, date="", other="", tables="") in guest_reply
        for k in ("admin_table_freed", "admin_table_already_free",
                  "admin_free_confirm", "admin_which_table",
                  "admin_table_not_found")),
        "الزبون: لا شيء من ردود الأدمن")
    check(texts.t("ar", "admin_only") not in guest_reply,
          "الزبون: ولا رسالة «هذا الأمر للأدمن فقط» — لا يعرف بوجودها")
    check(bool(guest_reply), "الزبون: وصله ردّ زبون عادي")

    # ------------------- 5) الأدمن زبوناً: الفصل بالمحتوى لا بالهوية
    print("\n5) الأدمن يبقى قادراً على استعمال بوته زبوناً")
    cleanup()
    msgs = say(boss, "بدي احجز طاولة")
    check(texts.t("ar", "ask_booking_type") in blob(msgs),
          "«بدي احجز طاولة» من الأدمن تفتح تدفق الحجز عادياً")

    cleanup()
    msgs = say(boss, "بكرا شخصين الساعة 4")
    check(texts.t("ar", "ask_booking_type") in blob(msgs),
          "واستخراج الحقول يعمل للأدمن كما للزبون")

    cleanup()
    msgs = say(boss, "شو عندكم أكل")
    check(bool(blob(msgs)) and "admin" not in blob(msgs).lower(),
          "وتصفّح المنيو يعمل له عادياً")

    # ولا يُخطف إدخال الاسم والهاتف وسط تدفقه
    cleanup()
    say(boss, "بكرا 4 اشخاص الساعة 5")
    conversation.handle_callback(boss, "B:t:family", "ar")
    msgs = say(boss, "أسامة")
    check(texts.t("ar", "ask_phone") in blob(msgs),
          "الاسم وسط تدفق الأدمن لا يُقرأ تعليمةً إدارية")
    msgs = say(boss, "0793239393")
    check(any(m["text"] and "http" in m["text"] for m in msgs)
          or texts.t("ar", "invalid_phone") not in blob(msgs),
          "والهاتف كذلك")

    # -------------------------------- 6) الغامض يُسأل بصفته أدمن
    print("\n6) التعليمة الغامضة: سؤال توضيحي إداري")
    cleanup()
    msgs = say(boss, "الطاولة %d" % number)
    check(texts.t("ar", "admin_free_confirm", table=number) in blob(msgs),
          "رقم طاولة بلا فعل -> سؤال توضيحي")
    buttons = [b for m in msgs for b in m["buttons"]]
    check("A:t:%d" % number in buttons, "وزر التأكيد يحمل رقم الطاولة")

    # الضمير يُحلّ بآخر طاولة ذُكرت
    msgs = say(boss, "عدلها على موقع الحجز")
    check(texts.t("ar", "admin_free_confirm", table=number) in blob(msgs),
          "«عدّلها» تُحلّ بالطاولة %d المذكورة قبلها" % number)

    # ولا هدف إطلاقاً
    cleanup()
    msgs = say(boss, "عدّل")
    check(texts.t("ar", "admin_which_table") in blob(msgs),
          "«عدّل» بلا سياق -> أي طاولة تقصد؟")

    # وزر التأكيد ينفّذ فعلاً
    cleanup()
    row = c.table("reservations").insert({
        "code": "ADM002", "platform": "telegram", "user_id": GUEST_UID,
        "customer_name": "ضيف", "customer_phone": "0790000000",
        "party_size": 2, "booking_type": "family", "table_id": table["id"],
        "reservation_date": today.isoformat(),
        "reservation_at": config.to_utc(when).isoformat(),
        "status": "confirmed",
    }).execute().data[0]
    sent.clear()
    conversation.handle_callback(boss, "A:t:%d" % number, "ar")
    check(db.get_reservation(row["id"])["status"] == "completed",
          "زر «نعم فضّيها» حرّر الطاولة فعلاً")
    sent.clear()
    conversation.handle_callback(boss, "A:tx:0", "ar")
    check(texts.t("ar", "admin_free_cancelled") in blob(sent),
          "وزر «لأ» لا يغيّر شيئاً")

    # الزبون لا يستطيع استعمال زر الأدمن
    c.table("reservations").update({"status": "confirmed"}).eq(
        "id", row["id"]).execute()
    sent.clear()
    conversation.handle_callback(guest, "A:t:%d" % number, "ar")
    check(db.get_reservation(row["id"])["status"] == "confirmed",
          "زبون يضغط زر الأدمن لا يحرّر شيئاً")

    # -------------------------- 6ب) الحجز الإداري — SPEC 10.2.1
    print("\n6ب) الحجز الإداري للطاولة: الوقت وحده، بلا اسم ولا هاتف")

    # لا يُطلب اسم ولا هاتف في أي من الحالتين — هذا هو جوهر الفحص.
    asks_identity = (texts.t("ar", "ask_name"), texts.t("ar", "ask_phone"),
                     texts.t("en", "ask_name"), texts.t("en", "ask_phone"))

    def free_table_now(num):
        """يعيد الطاولة متاحة قبل كل سيناريو."""
        tbl = next(t for t in db.all_tables() if t["table_number"] == num)
        for r in db.reservations_on(config.today_local().isoformat()):
            if r["table_id"] == tbl["id"]:
                # ترتيب إلزامي: الجلسات تشير إلى الحجوزات بمفتاح أجنبي.
                c.table("booking_sessions").delete().eq(
                    "reservation_id", r["id"]).execute()
                c.table("reservations").delete().eq("id", r["id"]).execute()
        return tbl

    # --- كل المعلومات بجملة واحدة: تنفيذ فوري بلا أي سؤال
    cleanup()
    target = free_table_now(number)
    msgs = say(boss, "الطاولة %d محجوزة الساعة 8" % number)
    reply = blob(msgs)
    check(len(msgs) == 1, "رسالة واحدة فقط — لا سؤال إضافي (%d)" % len(msgs))
    check(texts.t("ar", "admin_table_blocked", table=number,
                  date=admin._fmt_day(config.today_local(), "ar"),
                  time="8:00") in reply,
          "التأكيد: «%s»" % reply[:70])
    check(not any(q in reply for q in asks_identity),
          "لم يُطلب اسم ولا رقم هاتف")

    held = [r for r in db.reservations_on(config.today_local().isoformat())
            if r["table_id"] == target["id"]]
    check(len(held) == 1, "أُنشئ حجز واحد في القاعدة")
    row = held[0]
    check(row["status"] == "confirmed", "بحالة confirmed")
    check(row["platform"] == admin.BLOCK_PLATFORM
          and row["user_id"] == admin.BLOCK_USER,
          "على منصّة الأدمن لا على منصّة زبون")
    check(row["customer_name"] == texts.t("ar", "admin_block_name")
          and row["customer_phone"] == "—",
          "بلا اسم زبون ولا هاتف: %s / %s"
          % (row["customer_name"], row["customer_phone"]))
    check(row["party_size"] == target["capacity"],
          "العدد = سعة الطاولة (%d)" % row["party_size"])
    check(config.to_local(
        __import__("datetime").datetime.fromisoformat(
            row["reservation_at"])).hour == 20,
        "الساعة 8 مساءً كما ذُكرت في الجملة")
    check(target["id"] in db.booked_table_ids(
        config.today_local().isoformat()),
        "والطاولة اختفت من المتاحة — نفس استعلام الموقع")

    # لا تظهر في «حجوزاتي» لأحد ولا تلتقطها الجدولة
    check(not db.upcoming_for_user("telegram", ADMIN_UID,
                                   config.today_local().isoformat()),
          "لا تظهر في «حجوزاتي» للأدمن")
    import platform_adapter as _pa
    check(admin.BLOCK_PLATFORM not in _pa.ADAPTERS,
          "ومنصّتها بلا محوّل، فالجدولة تتخطّاها")

    # --- بلا وقت: سؤال واحد عن الساعة، ثم تنفيذ
    cleanup()
    target = free_table_now(number)
    msgs = say(boss, "الطاولة %d محجوزة" % number)
    reply = blob(msgs)
    check(texts.t("ar", "admin_ask_block_hour") in reply,
          "سُئل عن الساعة: «%s»" % reply[:50])
    check(not any(q in reply for q in asks_identity),
          "ولم يُطلب اسم ولا رقم هاتف")
    check(len(msgs) == 1, "سؤال واحد لا أكثر")
    check(not db.booked_table_ids(config.today_local().isoformat())
          .intersection({target["id"]}),
          "ولم يُنشأ حجز بعد")

    # الرقم المجرّد جوابٌ عن السؤال
    msgs = say(boss, "8")
    reply = blob(msgs)
    check(texts.t("ar", "admin_table_blocked", table=number,
                  date=admin._fmt_day(config.today_local(), "ar"),
                  time="8:00") in reply,
          "«8» وحدها نُفِّذت ساعةً: «%s»" % reply[:70])
    check(not any(q in reply for q in asks_identity),
          "ولا اسم ولا هاتف في هذه المرحلة أيضاً")
    check(target["id"] in db.booked_table_ids(
        config.today_local().isoformat()), "والطاولة صارت محجوزة")

    # --- التناظر: نفس الطاولة تُحرَّر بالأمر العادي
    msgs = say(boss, "الطاولة %d متاحة" % number)
    check(texts.t("ar", "admin_table_freed", table=number, date=admin._fmt_day(config.today_local(), "ar")) in blob(msgs),
          "والحجز الإداري يُحرَّر بنفس أمر التحرير")
    check(target["id"] not in db.booked_table_ids(
        config.today_local().isoformat()), "فتعود متاحة")

    # --- جواب غير صالح عن سؤال الساعة
    cleanup()
    free_table_now(number)
    say(boss, "الطاولة %d محجوزة" % number)
    msgs = say(boss, "مرحبا كيفك")
    check(texts.t("ar", "admin_block_bad_hour") in blob(msgs),
          "جواب ليس ساعةً -> يُعاد السؤال، بلا تشبّث أعمى")

    # --- طاولة عليها حجز أصلاً
    cleanup()
    target = free_table_now(number)
    say(boss, "الطاولة %d محجوزة الساعة 7" % number)
    msgs = say(boss, "الطاولة %d محجوزة الساعة 9" % number)
    check(texts.t("ar", "admin_table_taken", table=number,
                  date=admin._fmt_day(config.today_local(), "ar"))
          in blob(msgs), "طاولة محجوزة أصلاً لا تُحجز مرتين")
    free_table_now(number)

    # --- والزبون العادي لا يستطيع حجز طاولة إدارياً
    cleanup()
    target = free_table_now(number)
    msgs = say(guest, "الطاولة %d محجوزة الساعة 8" % number)
    check(target["id"] not in db.booked_table_ids(
        config.today_local().isoformat()),
        "زبون يقول «الطاولة محجوزة» لا يحجز شيئاً")
    check(texts.t("ar", "admin_ask_block_hour") not in blob(msgs),
          "ولا يُسأل سؤال الأدمن")

    # ------------------- 6ج) سياق المحادثة الإدارية (من محادثة فعلية)
    print("\n6ج) سياق المحادثة: التصحيح والوراثة")

    def free_now(num):
        tbl = next(t for t in db.all_tables() if t["table_number"] == num)
        for r in db.reservations_on(config.today_local().isoformat()):
            if r["table_id"] == tbl["id"]:
                # ترتيب إلزامي: الجلسات تشير إلى الحجوزات بمفتاح أجنبي.
                c.table("booking_sessions").delete().eq(
                    "reservation_id", r["id"]).execute()
                c.table("reservations").delete().eq("id", r["id"]).execute()
        return tbl

    # --- «احجزلي طاولة 20»: حجز مباشر لا سؤال غامض عن التحرير
    cleanup()
    target = free_now(number)
    msgs = say(boss, "احجزلي طاولة %d" % number)
    reply = blob(msgs)
    check(texts.t("ar", "admin_ask_block_hour") in reply,
          "«احجزلي طاولة %d» -> سؤال الساعة مباشرة" % number)
    check(texts.t("ar", "admin_free_confirm", table=number) not in reply,
          "ولا سؤال «قصدك تحدّث الحالة لمتاحة؟»")

    # --- التصحيح بعد سؤال توضيحي يحتفظ برقم الطاولة
    cleanup()
    target = free_now(number)
    msgs = say(boss, "الطاولة %d" % number)
    check(texts.t("ar", "admin_free_confirm", table=number) in blob(msgs),
          "سؤال توضيحي على الطاولة %d" % number)

    msgs = say(boss, "لا احجزها")
    reply = blob(msgs)
    check(texts.t("ar", "admin_ask_block_hour") in reply,
          "«لا احجزها» صُحّحت إلى حجز: «%s»" % reply[:50])
    check(texts.t("ar", "ask_date") not in reply
          and texts.t("ar", "ask_booking_type") not in reply,
          "ولم يبدأ تدفق زبون من الصفر")

    msgs = say(boss, "8")
    check(texts.t("ar", "admin_table_blocked", table=number,
                  date=admin._fmt_day(config.today_local(), "ar"),
                  time="8:00") in blob(msgs),
          "ورقم الطاولة %d بقي محفوظاً عبر التصحيح" % number)
    check(target["id"] in db.booked_table_ids(
        config.today_local().isoformat()), "فحُجزت فعلاً")

    # --- الإيجاب النصي يعمل كزر «نعم»
    cleanup()
    target = free_now(number)
    say(boss, "الطاولة %d" % number)
    msgs = say(boss, "اه")
    check(texts.t("ar", "admin_table_already_free", table=number, date=admin._fmt_day(config.today_local(), "ar"))
          in blob(msgs) or texts.t("ar", "admin_table_freed", table=number, date=admin._fmt_day(config.today_local(), "ar"))
          in blob(msgs), "«اه» جوابٌ عن السؤال لا تحيّةُ زبون")
    check(texts.t("ar", "greeting_back") not in blob(msgs)
          if texts.t("ar", "greeting_back") else True,
          "ولا ردّ ترحيبي")

    # --- والنفي المجرّد لا يغيّر شيئاً
    cleanup()
    free_now(number)
    say(boss, "الطاولة %d" % number)
    msgs = say(boss, "لأ")
    check(texts.t("ar", "admin_free_cancelled") in blob(msgs),
          "«لأ» تُلغي الاقتراح")

    # --- أمر جديد وسط سؤال معلّق لا يُقرأ جواباً عنه
    cleanup()
    other = next(t for t in db.all_tables()
                 if t["table_number"] != number and t["hall"] == "outdoor")
    free_now(number)
    free_now(other["table_number"])
    say(boss, "الطاولة %d" % number)
    msgs = say(boss, "الطاولة %d متاحة" % other["table_number"])
    check(texts.t("ar", "admin_table_already_free",
                  table=other["table_number"], date=admin._fmt_day(config.today_local(), "ar")) in blob(msgs)
          or texts.t("ar", "admin_table_freed",
                     table=other["table_number"], date=admin._fmt_day(config.today_local(), "ar")) in blob(msgs),
          "رسالة فيها رقم طاولة أمرٌ جديد لا جواب عن سؤال معلّق")

    # --- وراثة فعل الأمر السابق: «وطاولة X كمان»
    print("\n   وراثة الفعل السابق")
    for last, phrase, expect in [
            ("free", "وطاولة 36 كمان", ("free", ([36], None))),
            ("block", "وطاولة 36 كمان", ("block", ([36], None, None))),
            (None, "وطاولة 36 كمان", ("clarify_free", ([36], None)))]:
        got = admin_nlu.understand(phrase, last_action=last)
        check(got == expect, "آخر فعل %-5s -> %s" % (last, got))

    cleanup()
    target = free_now(number)
    other_t = free_now(other["table_number"])
    # نحجز الاثنتين ثم نحرّر الأولى بالأمر والثانية بالوراثة
    say(boss, "الطاولة %d محجوزة الساعة 7" % number)
    say(boss, "الطاولة %d محجوزة الساعة 7" % other["table_number"])
    say(boss, "الطاولة %d متاحة" % number)
    msgs = say(boss, "وطاولة %d كمان" % other["table_number"])
    reply = blob(msgs)
    check(texts.t("ar", "admin_table_freed",
                  table=other["table_number"], date=admin._fmt_day(config.today_local(), "ar")) in reply,
          "«وطاولة %d كمان» ورثت التحرير ونُفِّذت مباشرة"
          % other["table_number"])
    check(texts.t("ar", "admin_free_confirm",
                  table=other["table_number"]) not in reply,
          "بلا سؤال توضيحي")
    check(other_t["id"] not in db.booked_table_ids(
        config.today_local().isoformat()), "والطاولة تحرّرت فعلاً")
    free_now(number)
    free_now(other["table_number"])

    # ------------------- 6د) قوائم الطاولات والتواريخ وحارس السياق
    print("\n6د) قوائم الطاولات، التواريخ، وحارس السياق")

    from datetime import timedelta as _td
    tomorrow = config.today_local() + _td(days=1)

    def clear_table(num, when):
        tbl = next(t for t in db.all_tables() if t["table_number"] == num)
        for r in db.reservations_on(when.isoformat()):
            if r["table_id"] == tbl["id"]:
                c.table("booking_sessions").delete().eq(
                    "reservation_id", r["id"]).execute()
                c.table("reservations").delete().eq("id", r["id"]).execute()
        return tbl

    def guest_booking(num, when, code):
        tbl = clear_table(num, when)
        c.table("reservations").insert({
            "code": code, "platform": "telegram", "user_id": GUEST_UID,
            "customer_name": "ضيف", "customer_phone": "0790000000",
            "party_size": 4, "booking_type": "family", "table_id": tbl["id"],
            "reservation_date": when.isoformat(),
            "reservation_at": config.to_utc(
                booking.local_datetime(when, 22)).isoformat(),
            "status": "confirmed"}).execute()
        return tbl

    # --- التاريخ الصريح يُطبَّق فعلاً، لا يُفترض «اليوم»
    cleanup()
    t_a = guest_booking(20, tomorrow, "MD0001")
    t_b = guest_booking(21, tomorrow, "MD0002")
    check(t_a["id"] in db.booked_table_ids(tomorrow.isoformat()),
          "الطاولتان محجوزتان بكرا")

    msgs = say(boss, "حرر طاولة 20 و21 بكرا")
    check(texts.t("ar", "admin_tables_freed", tables="20 و21",
                  date=admin._fmt_day(tomorrow, "ar")) in blob(msgs),
          "أمرٌ بطاولتين وتاريخ نُفِّذ دفعةً واحدة")
    check(t_a["id"] not in db.booked_table_ids(tomorrow.isoformat())
          and t_b["id"] not in db.booked_table_ids(tomorrow.isoformat()),
          "الاثنتان تحرّرتا فعلاً يوم بكرا")

    # --- ثلاث طاولات
    cleanup()
    three = [guest_booking(n, tomorrow, "MD001%d" % i)
             for i, n in enumerate((20, 21, 22))]
    msgs = say(boss, "حرر طاولة 20 و21 و22 بكرا")
    check(all(t["id"] not in db.booked_table_ids(tomorrow.isoformat())
              for t in three), "أمرٌ بثلاث طاولات نُفِّذ على الثلاث")

    # --- تاريخ رقمي صريح 2/9
    cleanup()
    t_a = guest_booking(20, tomorrow, "MD0020")
    msgs = say(boss, "حرر طاولة 20 يوم %d/%d" % (tomorrow.day,
                                                 tomorrow.month))
    check(t_a["id"] not in db.booked_table_ids(tomorrow.isoformat()),
          "تاريخ رقمي %d/%d نُفِّذ عليه" % (tomorrow.day, tomorrow.month))

    # --- ما عليها حجز اليوم لكن عليها بكرا: يُسأل ولا يُفترض
    cleanup()
    t_a = guest_booking(20, tomorrow, "MD0030")
    t_b = guest_booking(21, tomorrow, "MD0031")
    clear_table(20, config.today_local())
    clear_table(21, config.today_local())
    msgs = say(boss, "بدي تحول طاولة 20 و21 لمتاح")
    reply = blob(msgs)
    check(texts.t("ar", "admin_maybe_other_day", table="20 و21",
                  date=admin._fmt_day(config.today_local(), "ar"),
                  other=admin._fmt_day(tomorrow, "ar")) in reply,
          "سؤالٌ واحد عن اليوم للطاولتين معاً")
    check(len(msgs) == 1, "لا سؤال مكرّر لكل طاولة (%d رسالة)" % len(msgs))
    check(t_a["id"] in db.booked_table_ids(tomorrow.isoformat()),
          "ولم يُحرَّر شيء قبل الجواب")

    # --- والجواب «بكرة مو اليوم» يُنفَّذ على الطاولتين
    msgs = say(boss, "بكرة مو اليوم")
    check(texts.t("ar", "admin_tables_freed", tables="20 و21",
                  date=admin._fmt_day(tomorrow, "ar")) in blob(msgs),
          "«بكرة مو اليوم» حرّرت الطاولتين معاً")
    check(t_a["id"] not in db.booked_table_ids(tomorrow.isoformat())
          and t_b["id"] not in db.booked_table_ids(tomorrow.isoformat()),
          "الاثنتان تحرّرتا")

    # --- حارس السياق: لا نزول إلى ترحيب الزبون أبداً
    print("\n   حارس السياق الإداري")
    greeting = texts.t("ar", "welcome_back") or texts.t("ar", "welcome")
    check(bool(greeting), "نصّ الترحيب موجود فعلاً")

    cleanup()
    guest_booking(20, tomorrow, "MD0040")
    clear_table(20, config.today_local())
    say(boss, "الطاولة 20 متاحة")          # ينتهي بسؤال عن اليوم
    for confusing in ["بكرة مو اليوم", "اه", "يعني شو",
                      "خليها زي ما هي بكرا"]:
        msgs = say(boss, confusing)
        reply = blob(msgs)
        check(greeting not in reply,
              "«%s» -> لا ترحيب زبون" % confusing)
        check(texts.t("ar", "btn_menu") not in
              " ".join(b for m in msgs for b in m["buttons"]),
              "  ولا أزرار تصفّح")

    # وبعد أمر نُفِّذ وانتهى — التسريب وقع هنا بلا حالة معلّقة
    cleanup()
    say(boss, "الطاولة 20 متاحة")
    msgs = say(boss, "بكرة مو اليوم")
    check(greeting not in blob(msgs),
          "شظيّة تاريخ بعد أمر منتهٍ -> لا ترحيب")

    # لكن سؤالاً حقيقياً بلا شظيّة يبقى في مسار الزبون
    msgs = say(boss, "شو عندكم أكل")
    check(bool(blob(msgs)), "وسؤال المنيو يبقى يعمل للأدمن")
    check(not admin_nlu.has_admin_fragment("قديش سعر التبولة"),
          "سؤال سعر ليس شظيّة إدارية")

    # --- الردّ الإداري بلا لوحة أزرار الزبون
    print("\n   لوحة أزرار الزبون خارج المحادثة الإدارية")
    cleanup()
    plains = []

    class Plain(Fake):
        def send_text(self, user, text, plain=False):
            plains.append(plain)
            sent.append({"to": user.user_id, "text": text, "buttons": []})

    platform_adapter.ADAPTERS["telegram"] = Plain()
    say(boss, "الطاولة 20 متاحة")
    check(plains and all(plains), "كل ردٍّ إداري يمسح لوحة الزبون")
    platform_adapter.ADAPTERS["telegram"] = Fake()

    # ------------------------------------------- 7) نبرة الأسئلة
    print("\n7) دفء نبرة أسئلة بداية الحجز")
    cold = ("قبل ما نبلّش", "اختر الساعة:", "كم شخص رح تكونوا؟")
    for phrase in cold:
        check(all(phrase != texts.t("ar", k) for k in
                  ("ask_booking_type", "ask_hour", "ask_party")),
              "لم تبقَ الصياغة الجافة «%s»" % phrase)
    warm_keys = ("ask_booking_type", "ask_date", "ask_period", "ask_hour",
                 "ask_party", "ask_name", "ask_phone")
    for key in warm_keys:
        for lang in ("ar", "en"):
            body = texts.t(lang, key)
            check(bool(body.strip()) and len(body) <= 90,
                  "%s/%s: «%s»" % (key, lang, body))

    cleanup()
    c.table("admins").delete().eq("user_id", ADMIN_UID).execute()
    print("\n" + "=" * 70)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
