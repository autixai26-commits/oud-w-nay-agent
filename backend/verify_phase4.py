# -*- coding: utf-8 -*-
"""تحقق المرحلة 4 — الأدمن والجدولة.

    python backend/verify_phase4.py

ينفّذ سيناريو الحجز كاملاً بأوقات مضغوطة كما تطلب SPEC القسم 12:
يضبط TEST_TIME_SCALE=60 فتصير كل دقيقة ثانية، ويمر بالمسار من إنشاء
الحجز حتى الإلغاء التلقائي خلال أقل من دقيقة حقيقية.

لا تُرسل أي رسالة فعلية لتليجرام — الإرسال ملتقط بالكامل.
يخرج بالرمز 1 عند أي فشل. كل بيانات الاختبار تُحذف في النهاية.
"""
import os
import sys
import time
from pathlib import Path

# يجب أن يسبق استيراد config: load_dotenv لا يطغى على متغيّر موجود.
os.environ["TEST_TIME_SCALE"] = "60"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import admin          # noqa: E402
import booking        # noqa: E402
import config         # noqa: E402
import conversation   # noqa: E402
import db             # noqa: E402
import platform_adapter  # noqa: E402
import scheduler      # noqa: E402
import telegram_api   # noqa: E402
import texts          # noqa: E402
from platform_adapter import User  # noqa: E402

UID = "__v4_cust__"
ADMIN_ID = "__v4_admin__"
ok = True
to_customer: list = []
to_admin: list = []


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class Fake(platform_adapter.BaseAdapter):
    """يلتقط الرسائل بدل إرسالها، ويفرزها حسب المستقبِل."""
    platform = "telegram"

    @staticmethod
    def _put(user, text):
        if str(user.user_id) == ADMIN_ID:
            to_admin.append({"chat_id": ADMIN_ID, "text": text, "markup": None})
        else:
            to_customer.append(text)

    def send_text(self, user, text):
        self._put(user, text)

    def send_buttons(self, user, text, buttons, nav=None):
        platform_adapter._validate(buttons)
        self._put(user, text)

    def send_link(self, user, text, label, url):
        self._put(user, text)


def fake_send_message(chat_id, text, reply_markup=None):
    """يلتقط رسائل الأدمن — admin.py ينادي telegram_api مباشرة."""
    to_admin.append({"chat_id": str(chat_id), "text": text,
                     "markup": reply_markup})
    return {"ok": True, "result": {"message_id": len(to_admin)}}


def fake_edit(chat_id, message_id, text, reply_markup=None):
    to_admin.append({"chat_id": str(chat_id), "text": text, "edit": True})
    return {"ok": True}


def cleanup() -> None:
    c = db.client()
    c.table("booking_sessions").delete().eq("user_id", UID).execute()
    c.table("reservations").delete().eq("user_id", UID).execute()
    c.table("user_state").delete().eq("user_id", UID).execute()
    c.table("admins").delete().eq("user_id", ADMIN_ID).execute()


def wait(seconds: float, label: str) -> None:
    print("     … انتظار %.0f ثانية (%s)" % (seconds, label))
    time.sleep(seconds)


def main() -> int:
    global ok
    print("=" * 62)
    print("تحقق المرحلة 4 — الأدمن والجدولة")
    print("=" * 62)
    print("TEST_TIME_SCALE = %s  →  كل دقيقة تساوي %.1f ثانية"
          % (config.TEST_TIME_SCALE, config.minutes(1).total_seconds()))

    platform_adapter.ADAPTERS["telegram"] = Fake()
    telegram_api.send_message = fake_send_message
    telegram_api.edit_message_text = fake_edit

    cleanup()
    cust = User("telegram", UID, UID)
    adm = User("telegram", ADMIN_ID, ADMIN_ID)

    # ------------------------------------------- 1) تسجيل الأدمن
    print("\n1) تسجيل الأدمن (SPEC 10.1)")
    check(admin.try_register(adm, "wrong-secret", "") == "admin_bad_secret",
          "سر خاطئ يُرفض")
    check(not db.is_admin("telegram", ADMIN_ID), "لم يُسجَّل بالسر الخاطئ")
    check(admin.try_register(adm, config.ADMIN_SETUP_SECRET, "مدير")
          == "admin_registered", "السر الصحيح يسجّل الأدمن")
    check(db.is_admin("telegram", ADMIN_ID), "صار أدمن في قاعدة البيانات")
    check(admin.try_register(adm, config.ADMIN_SETUP_SECRET, "")
          == "admin_already", "التسجيل مرتين لا يكرّر")

    # الأدمن يسجّل نفسه قبل أن يختار لغة. لو ابتلعت بوابةُ اللغة الأمرَ
    # لتعذّر التسجيل إطلاقاً — وهذا ما حدث فعلاً على البوت الحي.
    db.client().table("admins").delete().eq("user_id", ADMIN_ID).execute()
    db.client().table("user_state").delete().eq("user_id", ADMIN_ID).execute()
    to_customer.clear(); to_admin.clear()
    conversation.handle_text(adm, "/admin " + config.ADMIN_SETUP_SECRET, None)
    check(db.is_admin("telegram", ADMIN_ID),
          "/admin يعمل لمستخدم جديد بلا لغة محفوظة")
    to_customer.clear(); to_admin.clear()
    conversation.handle_text(User("telegram", "__nolang__", "__nolang__"),
                             "مرحبا", None)
    check(any("لغتك" in m for m in to_customer),
          "الرسالة العادية بلا لغة ما زالت تعرض شاشة اللغة")
    db.client().table("user_state").delete().eq(
        "user_id", "__nolang__").execute()

    # ------------------------------- 2) حجز جديد وإشعار الأدمن
    print("\n2) حجز جديد وإشعار الأدمن (SPEC 6.3.2)")
    day = config.today_local()
    # الموعد بعد 40 دقيقة مضغوطة = 40 ثانية حقيقية. المسافة ضرورية
    # لتنفصل المراحل: التذكير عند الموعد−30، سؤال الحضور عند +10،
    # والإلغاء التلقائي عند +30.
    target_utc = config.now_utc() + config.minutes(40)
    table = booking.available_tables(day, 2, "family")[0]

    res = db.client().table("reservations").insert({
        "code": "V4TEST", "platform": "telegram", "user_id": UID,
        "customer_name": "زبون اختبار", "customer_phone": "0790000000",
        "party_size": 2, "booking_type": "family", "table_id": table["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": target_utc.isoformat(),
        "status": "pending", "language": "ar",
    }).execute().data[0]

    to_admin.clear()
    admin.notify_new_reservation(res)
    check(len(to_admin) == 1, "وصل إشعار لكل الأدمنية (%d)" % len(to_admin))
    body = to_admin[0]["text"]
    check(all(x in body for x in ("V4TEST", "زبون اختبار", "0790000000")),
          "الإشعار يحوي الرمز والاسم والهاتف")
    labels = [b[0]["text"] for b in (to_admin[0]["markup"] or {}).get(
        "inline_keyboard", [])]
    check(texts.t("ar", "btn_admin_confirm") in labels
          and texts.t("ar", "btn_admin_reject") in labels,
          "الإشعار فيه زرّا التثبيت والرفض")

    # -------------------------- 3) التنبيه الثاني بعد 15 دقيقة
    print("\n3) التنبيه الثاني بعد 15 دقيقة بلا رد (SPEC 6.3.5)")
    to_admin.clear(); to_customer.clear()
    check(scheduler.tick()["alert2"] == 0, "لا تنبيه قبل انقضاء المدة")
    wait(16, "15 دقيقة مضغوطة")
    counts = scheduler.tick()
    check(counts["alert2"] == 1, "انطلق التنبيه الثاني")
    alert_head = texts.AR["admin_alert2"].split("{")[0].strip()
    check(any(alert_head in m["text"] for m in to_admin),
          "وصل التنبيه للأدمن")
    check(any("10" in m for m in to_customer),
          "وصلت رسالة الانتظار للزبون مع رقم الهاتف")
    check(scheduler.tick()["alert2"] == 0, "لا يتكرّر التنبيه في الدورة التالية")

    # ------------------------------------- 4) تثبيت الأدمن
    print("\n4) تثبيت الحجز (SPEC 6.3.3)")
    to_customer.clear(); to_admin.clear()
    check(admin.decide(res["id"], True, "مدير") == "confirmed",
          "الحالة صارت confirmed")
    check(any("V4TEST" in m for m in to_customer),
          "وصلت رسالة التأكيد للزبون مع رمز الحجز")
    check(any(m.get("edit") for m in to_admin),
          "عُدِّلت رسالة الأدمن لتعطيل الأزرار (SPEC 6.3.6)")
    check(admin.decide(res["id"], False, "آخر") is None,
          "رد ثانٍ لا يغيّر شيئاً — أول رد يُعتمد")

    # -------------------------------- 5) تذكير الزبون قبل الموعد
    print("\n5) تذكير الزبون قبل الموعد بـ30 دقيقة (SPEC 6.4)")
    to_customer.clear()
    counts = scheduler.tick()
    check(counts["reminder"] == 1, "انطلق التذكير")
    rem_head = texts.AR["reminder"].split("{")[0].strip()
    check(any(rem_head in m for m in to_customer), "وصل التذكير للزبون")
    check(scheduler.tick()["reminder"] == 0, "لا يتكرّر التذكير")

    # ------------------------- 6) سؤال الحضور بعد الموعد بـ10 دقائق
    print("\n6) سؤال الحضور بعد الموعد (SPEC 6.4)")
    wait(30, "الموعد + 10 دقائق مضغوطة")
    to_admin.clear()
    counts = scheduler.tick()
    check(counts["attendance"] == 1, "انطلق سؤال الحضور")
    check(any("إجا" in m["text"] or "arrive" in m["text"].lower()
              for m in to_admin), "وصل السؤال للأدمن")
    check(scheduler.tick()["attendance"] == 0, "لا يتكرّر السؤال")

    # --------------------------------- 7) الإلغاء التلقائي
    print("\n7) الإلغاء التلقائي بعد الموعد بـ30 دقيقة (SPEC 6.4)")
    wait(25, "الموعد + 30 دقيقة مضغوطة")
    to_customer.clear(); to_admin.clear()
    counts = scheduler.tick()
    check(counts["auto_cancel"] == 1, "انطلق الإلغاء التلقائي")
    fresh = db.get_reservation(res["id"])
    check(fresh["status"] == "no_show", "الحالة صارت no_show")
    check(table["id"] not in db.booked_table_ids(day.isoformat()),
          "تحرّرت الطاولة فوراً")
    cancel_head = texts.AR["auto_cancelled_customer"].split(chr(10))[0]
    check(any(cancel_head in m for m in to_customer), "وصل إشعار للزبون")
    check(len(to_admin) >= 1, "وصل إشعار للأدمن")

    # ------------------------------- 8) الحضور والتحرير اليدوي
    print("\n8) تسجيل الحضور وتحرير الطاولة (SPEC 6.4 و 10.2)")
    res2 = db.client().table("reservations").insert({
        "code": "V4SEAT", "platform": "telegram", "user_id": UID,
        "customer_name": "زبون ثانٍ", "customer_phone": "0790000001",
        "party_size": 2, "booking_type": "family", "table_id": table["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": config.now_utc().isoformat(),
        "status": "confirmed", "language": "ar",
    }).execute().data[0]
    check(admin.mark_attendance(res2["id"], True, "مدير") == "seated",
          "«إجا» تجعل الحالة seated")
    check(table["id"] in db.booked_table_ids(day.isoformat()),
          "الطاولة تبقى مقفلة وهو جالس")
    check(admin.free_table(res2["id"]) == "completed",
          "«الطاولة فضيت» تجعل الحالة completed")
    check(table["id"] not in db.booked_table_ids(day.isoformat()),
          "الطاولة عادت متاحة فوراً في نفس اليوم (SPEC 5.6)")

    # ------------------------- 9) إلغاء الزبون بلا موافقة أدمن
    print("\n9) إلغاء الزبون لحجزه (SPEC 6.5)")
    res3 = db.client().table("reservations").insert({
        "code": "V4CANC", "platform": "telegram", "user_id": UID,
        "customer_name": "زبون ثالث", "customer_phone": "0790000002",
        "party_size": 2, "booking_type": "family", "table_id": table["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": config.now_utc().isoformat(),
        "status": "confirmed", "language": "ar",
    }).execute().data[0]
    to_admin.clear(); to_customer.clear()
    conversation.handle_callback(cust, "R:x:%d" % res3["id"], "ar")
    fresh3 = db.get_reservation(res3["id"])
    check(fresh3["status"] == "cancelled", "الحالة صارت cancelled فوراً")
    check(table["id"] not in db.booked_table_ids(day.isoformat()),
          "تحرّرت الطاولة")
    check(len(to_admin) >= 1, "وصل إشعار للأدمن بما حصل")

    # ------------------------------------- 10) أوامر الأدمن
    print("\n10) أوامر الأدمن (SPEC 10.2)")
    to_admin.clear(); to_customer.clear()
    check(admin.handle_command(cust, "/today", "ar") is True,
          "/today يُستهلك")
    check(any(texts.t("ar", "admin_only") in m for m in to_customer),
          "غير الأدمن يُمنع من /today")
    to_customer.clear()
    for cmd in ("/today", "/stats", "/help", "/date 2026-09-01",
                "/free 999", "/cancel NOPE00"):
        to_admin.clear()
        handled = admin.handle_command(adm, cmd, "ar")
        check(handled and len(to_admin) >= 1, "%-22s ردّ على الأدمن" % cmd)
    check(admin.handle_command(adm, "/notacommand", "ar") is False,
          "أمر مجهول لا يُستهلك فيصل للأسئلة الحرة")

    cleanup()
    print("\n" + "=" * 62)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cleanup()
    raise SystemExit(code)
