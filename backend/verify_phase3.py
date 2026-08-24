# -*- coding: utf-8 -*-
"""تحقق المرحلة 3 — تدفق الحجز وقواعد القسم 5 وواجهة الموقع.

    python backend/verify_phase3.py

يغطّي حالتَي التحقق المنصوص عليهما في SPEC القسم 12 للمرحلة 3:
  * حجز شباب يوم خميس يُرفض قبل توليد أي رابط.
  * حجز شباب يوم أحد يفتح الموقع بصالتين داخليتين مقفولتين.
ويضيف: قاعدة اليوم الكامل، الرابط لاستعمال واحد، الهابي أور، والسعة.

يخرج بالرمز 1 عند أي فشل. كل بيانات الاختبار تُحذف في النهاية.
"""
import sys
from datetime import date as Date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import booking
import config
import conversation
import db
import platform_adapter
import texts
from platform_adapter import User

UID = "__verify3__"
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
    # ترتيب إلزامي: الجلسات تشير إلى الحجوزات بمفتاح أجنبي.
    c.table("booking_sessions").delete().eq("user_id", UID).execute()
    c.table("reservations").delete().eq("user_id", UID).execute()
    c.table("user_state").delete().eq("user_id", UID).execute()


def run_flow(user, lang, steps) -> list:
    """ينفّذ سلسلة ضغطات وكتابات ويعيد كل ما أُرسل."""
    out = []
    for step in steps:
        sent.clear()
        if step.startswith("#"):
            conversation.handle_text(user, step[1:], lang)
        else:
            conversation.handle_callback(user, step, lang)
        out.extend(sent)
    return out


def main() -> int:
    print("=" * 60)
    print("تحقق المرحلة 3 — الحجز والموقع")
    print("=" * 60)

    platform_adapter.ADAPTERS["telegram"] = Fake()
    user = User("telegram", UID, UID)
    cleanup()

    days = booking.next_days()
    sunday = next(d for d in days if d.weekday() == 6)
    thursday = next(d for d in days if d.weekday() == 3)
    tuesday = next(d for d in days if d.weekday() == 1)
    friday = next(d for d in days if d.weekday() == 4)

    # ---------------------------------------------- 1) الرفض المبكر
    print("\n1) حجز شباب يوم خميس — يُرفض قبل الرابط (SPEC 5.4)")
    msgs = run_flow(user, "ar", ["B", "B:t:singles",
                                 "B:d:%s" % thursday.isoformat()])
    blob = "\n".join(m["text"] for m in msgs)
    check(texts.t("ar", "singles_family_day") in blob,
          "ظهرت رسالة الرفض")
    check(not any(m["link"] for m in msgs), "لم يُرسل أي رابط")
    sessions = (db.client().table("booking_sessions").select("id")
                .eq("user_id", UID).execute().data)
    check(not sessions, "لم تُنشأ أي جلسة حجز في قاعدة البيانات")

    # ------------------------------------- 2) شباب يوم أحد: قفل الصالات
    print("\n2) حجز شباب يوم أحد — الصالتان الداخليتان مقفولتان (SPEC 5.5)")
    cleanup()
    msgs = run_flow(user, "ar", [
        "B", "B:t:singles", "B:d:%s" % sunday.isoformat(),
        "B:p:evening", "B:h:19", "B:n:4", "#سامر", "#0791234567"])
    link = next((m["link"] for m in msgs if m["link"]), None)
    check(link is not None, "وصل رابط اختيار الطاولة")

    token = (db.client().table("booking_sessions").select("token")
             .eq("user_id", UID).execute().data[0]["token"])
    session = booking.get_session(token)
    halls = booking.hall_map(sunday, session["party_size"],
                             session["booking_type"])
    check(not halls["outdoor"]["locked"], "الخارجية مفتوحة")
    check(halls["main"]["locked"] and halls["narrow"]["locked"],
          "الكبيرة والضيقة مقفولتان")
    inner = sum(1 for h in ("main", "narrow")
                for t in halls[h]["tables"] if t["selectable"])
    check(inner == 0, "لا طاولة داخلية قابلة للضغط (%d)" % inner)
    try:
        booking.create_reservation(token, halls["main"]["tables"][0]["id"])
        check(False, "الـAPI رفض حجز طاولة داخلية")
    except booking.BookingError as exc:
        check(str(exc) == "hall_not_allowed",
              "الـAPI رفض حجز طاولة داخلية (%s)" % exc)

    # ------------------------------------------ 3) قاعدة اليوم الكامل
    print("\n3) قفل الطاولة وقاعدة اليوم الكامل (SPEC 5.6 و 6.2)")
    cleanup()

    def session_for(day, party=4, kind="family"):
        return booking.create_session(
            platform="telegram", user_id=UID, booking_type=kind,
            party_size=party, day=day, hour=19, name="اختبار",
            phone="0790000000", language="ar")["token"]

    t1 = session_for(sunday)
    target = booking.available_tables(sunday, 4, "family")[0]
    booking.create_reservation(t1, target["id"])
    check(target["id"] in db.booked_table_ids(sunday.isoformat()),
          "الطاولة أُقفلت فور التأكيد")
    t2 = session_for(sunday)
    try:
        booking.create_reservation(t2, target["id"])
        check(False, "زبون ثانٍ يُرفض على نفس الطاولة")
    except booking.BookingError as exc:
        check(str(exc) == "taken", "زبون ثانٍ يُرفض بسبب taken")
    check(target["id"] not in db.booked_table_ids(thursday.isoformat()),
          "نفس الطاولة متاحة في يوم آخر — الخريطة تُصفَّر")

    # -------------------------------------- 4) الرابط لاستعمال واحد
    print("\n4) الرابط لاستعمال واحد وصلاحيته 30 دقيقة (SPEC 6.1.8)")
    check(booking.session_state(booking.get_session(t1)) == "used",
          "الرابط صار used بعد الحجز")
    check(booking.session_state(None) == "not_found", "رابط مجهول: not_found")
    ttl = config.minutes(config.BOOKING_LINK_TTL_MIN)
    check(abs(ttl.total_seconds() - 1800) < 1,
          "مدة الصلاحية 30 دقيقة عبر minutes() (%s)" % ttl)

    # ------------------------------------------------ 5) الهابي أور
    print("\n5) الهابي أور (SPEC 3 و 6.1.7)")
    check(booking.is_happy_hour(booking.local_datetime(tuesday, 15)),
          "3 عصراً يوم ثلاثاء ضمن الهابي أور")
    check(not booking.is_happy_hour(booking.local_datetime(friday, 15)),
          "3 عصراً يوم جمعة خارجه — الجمعة مستثناة")
    cleanup()
    msgs = run_flow(user, "ar", [
        "B", "B:t:family", "B:d:%s" % tuesday.isoformat(),
        "B:p:noon", "B:h:15", "B:n:4", "#ليان", "#0791234567"])
    blob = "\n".join(m["text"] for m in msgs)
    check(texts.t("ar", "happy_hour_notice") in blob,
          "التنويه ظهر قبل الرابط")

    # -------------------------------------------------- 6) السعة
    print("\n6) الطاولات المعروضة حسب السعة (SPEC 5.7)")
    cleanup()
    for party in (2, 8, 10):
        rows = booking.available_tables(sunday, party, "family")
        bad = [t["table_number"] for t in rows if t["capacity"] < party]
        check(not bad, "%2d أشخاص -> %2d طاولة، ولا واحدة أصغر من العدد"
              % (party, len(rows)))

    # --------------------------------------- 7) المجموعات الكبيرة
    print("\n7) المجموعة الكبيرة 11+ (SPEC 5.8)")
    cleanup()
    msgs = run_flow(user, "ar", [
        "B", "B:t:family", "B:d:%s" % sunday.isoformat(),
        "B:p:noon", "B:h:15", "B:n:11", "#14", "#سامر", "#0791234567",
        "B:g:wedding", "#خطوبة"])
    check(not any(m["link"] for m in msgs), "لم يُرسل أي رابط")
    rows = (db.client().table("reservations").select("*")
            .eq("user_id", UID).execute().data)
    check(len(rows) == 1 and rows[0]["is_large_group"],
          "أُنشئ طلب يدوي بعلامة is_large_group")
    check(rows[0]["table_id"] is None, "بلا طاولة")
    check(rows[0]["party_size"] == 14 and rows[0]["group_type"] == "wedding",
          "العدد 14 ونوع المجموعة عرس")

    # ----------------------------------------- 8) حدود الأزرار
    print("\n8) حدود الأزرار في تدفق الحجز (SPEC 7.1 و 11)")
    cleanup()
    msgs = run_flow(user, "ar", [
        "B", "B:t:family", "B:d:%s" % sunday.isoformat(), "B:p:evening"])
    worst = max((len(m["buttons"]) for m in msgs), default=0)
    check(worst <= platform_adapter.MAX_OPTIONS_PER_LEVEL,
          "أقصى خيارات في مستوى: %d (الحد %d)"
          % (worst, platform_adapter.MAX_OPTIONS_PER_LEVEL))
    worst_nav = max((len(m["nav"]) for m in msgs), default=0)
    check(worst_nav <= platform_adapter.MAX_QUICK_BUTTONS,
          "أقصى أزرار تنقّل: %d (الحد %d)"
          % (worst_nav, platform_adapter.MAX_QUICK_BUTTONS))

    cleanup()
    print("\n" + "=" * 60)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
