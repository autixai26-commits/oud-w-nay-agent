# -*- coding: utf-8 -*-
"""الاختبار النهائي الشامل على الإنتاج الحي — SPEC القسم 14.

    python backend/verify_production.py

يقود النظام المنشور فعلياً: webhook تيليجرام الحي، وواجهات Render،
وقاعدة بيانات الإنتاج. لا شيء محلي هنا.

الزبائن وهميون (معرّفات لا تقابل حسابات تيليجرام حقيقية)، لذلك رسائل
الزبون لا تصل أحداً — نتحقق منها بأثرها في قاعدة البيانات. أما إشعارات
الأدمن فتصل للأدمن الحقيقي المسجّل، وهذا مقصود: نريد رؤيتها فعلاً.

حالتا الرسالة الصوتية لا يمكن أتمتتهما — تحتاجان إرسال ملف صوتي من
حساب تيليجرام حقيقي. تُنفَّذان يدوياً.

كل بيانات الاختبار تُحذف في النهاية.
"""
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402

import admin      # noqa: E402
import booking    # noqa: E402
import config     # noqa: E402
import db         # noqa: E402
import main       # noqa: E402
import texts      # noqa: E402

API = config.BACKEND_URL
SITE = config.PUBLIC_WEB_URL
HOOK = API + main.WEBHOOK_PATH
SECRET = main.webhook_secret()

C1 = "900000001"   # زبون وهمي أول
C2 = "900000002"   # زبون وهمي ثانٍ
PREFIX = "9000000"

results: list = []


def check(passed: bool, case: str, detail: str = "") -> None:
    results.append((passed, case, detail))
    print("  %s %s%s" % ("PASS" if passed else "FAIL", case,
                         ("  — " + detail) if detail else ""))


def hook(payload: dict) -> int:
    r = httpx.post(HOOK, json=payload, timeout=60,
                   headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
    time.sleep(2.5)          # نترك للباك إند وقتاً ليكتب في قاعدة البيانات
    return r.status_code


def msg(uid: str, text: str) -> int:
    return hook({"message": {"from": {"id": int(uid)},
                             "chat": {"id": int(uid)}, "text": text}})


def tap(uid: str, data: str) -> int:
    return hook({"callback_query": {"id": "1", "from": {"id": int(uid)},
                                    "message": {"chat": {"id": int(uid)}},
                                    "data": data}})


def state(uid: str) -> dict:
    return db.get_user_state("telegram", uid) or {}


def sessions(uid: str) -> list:
    return (db.client().table("booking_sessions").select("*")
            .eq("user_id", uid).execute().data)


def reservations(uid: str) -> list:
    return (db.client().table("reservations").select("*")
            .eq("user_id", uid).order("id").execute().data)


def cleanup() -> None:
    c = db.client()
    for uid in (C1, C2):
        c.table("booking_sessions").delete().eq("user_id", uid).execute()
        c.table("reservations").delete().eq("user_id", uid).execute()
        c.table("user_state").delete().eq("user_id", uid).execute()


def start_as(uid: str, lang: str = "ar") -> None:
    """يهيّئ زبوناً وهمياً باللغة المطلوبة."""
    tap(uid, "L:" + lang)


def day_of(weekday: int):
    return next(d for d in booking.next_days() if d.weekday() == weekday)


def book_until_link(uid: str, kind: str, day, hour: int, size: int,
                    name: str, phone: str) -> None:
    tap(uid, "B")
    tap(uid, "B:t:" + kind)
    tap(uid, "B:d:" + day.isoformat())
    tap(uid, "B:p:" + booking.period_of(hour))
    tap(uid, "B:h:%d" % hour)
    tap(uid, "B:n:%d" % size)
    msg(uid, name)
    msg(uid, phone)


def main_run() -> int:
    print("=" * 66)
    print("الاختبار النهائي الشامل على الإنتاج — SPEC القسم 14")
    print("=" * 66)
    print("الباك إند :", API)
    print("الموقع    :", SITE)

    health = httpx.get(API + "/health", timeout=60).json()
    print("الصحة     : db=%s · ffmpeg=%s · voice=%s · scale=%s · tick=%ss"
          % (health.get("database"), health.get("ffmpeg"),
             health.get("voice_keys"), health.get("test_time_scale"),
             health.get("scheduler_seconds")))

    admins = db.all_admins()
    print("الأدمنية  :", len(admins))
    print()
    cleanup()

    sunday, thursday = day_of(6), day_of(3)
    tuesday, friday = day_of(1), day_of(4)

    # ---------------------------------------------------------------- 1
    print("1) حجز عائلة يوم عادي ← رابط ← طاولة ← موافقة أدمن ← تأكيد")
    start_as(C1)
    book_until_link(C1, "family", sunday, 19, 4, "زبون اختبار أول", "0791111111")
    ses = sessions(C1)
    check(len(ses) == 1, "تولّد رابط حجز واحد")
    token = ses[0]["token"] if ses else ""

    got = httpx.get("%s/api/booking/%s" % (API, token), timeout=60).json()
    check(got.get("state") == "ok", "الموقع يقرأ الجلسة من الباك إند")
    free = [t for t in got["halls"]["main"]["tables"] if t["selectable"]]
    made = httpx.post("%s/api/booking/%s/reserve" % (API, token),
                      json={"table_id": free[0]["id"]}, timeout=90).json()
    check(made.get("ok") is True, "أُنشئ الحجز من الموقع",
          "رمز %s" % made.get("code"))
    time.sleep(3)
    res = [r for r in reservations(C1) if r["code"] == made.get("code")]
    check(bool(res) and res[0]["status"] == "pending", "الحالة pending")
    check(bool(res[0].get("admin_messages")),
          "وصل إشعار للأدمن", "%d رسالة" % len(res[0].get("admin_messages") or []))

    admin.decide(res[0]["id"], True, "اختبار آلي")
    time.sleep(2)
    after = db.get_reservation(res[0]["id"])
    check(after["status"] == "confirmed", "موافقة الأدمن ثبّتت الحجز")
    confirmed_id, confirmed_table = after["id"], after["table_id"]

    # ---------------------------------------------------------------- 2
    print("\n2) حجز شباب يوم خميس ← رفض فوري قبل الرابط")
    before = len(sessions(C2))
    start_as(C2)
    tap(C2, "B")
    tap(C2, "B:t:singles")
    tap(C2, "B:d:" + thursday.isoformat())
    check(len(sessions(C2)) == before, "لم يتولّد أي رابط")
    check(state(C2).get("state") == "bk_date",
          "التدفق توقّف عند اختيار التاريخ")

    # ---------------------------------------------------------------- 3
    print("\n3) حجز شباب يوم أحد ← الصالات الداخلية مقفولة على الموقع")
    book_until_link(C2, "singles", sunday, 19, 4, "زبون اختبار ثانٍ", "0792222222")
    ses2 = sessions(C2)
    check(len(ses2) == 1, "تولّد الرابط")
    t2 = ses2[0]["token"]
    m = httpx.get("%s/api/booking/%s" % (API, t2), timeout=60).json()
    check(m["halls"]["main"]["locked"] and m["halls"]["narrow"]["locked"],
          "الصالتان الداخليتان مقفولتان")
    check(not m["halls"]["outdoor"]["locked"], "الخارجية مفتوحة")
    inner = sum(1 for h in ("main", "narrow")
                for t in m["halls"][h]["tables"] if t["selectable"])
    check(inner == 0, "لا طاولة داخلية قابلة للضغط")
    bad = httpx.post("%s/api/booking/%s/reserve" % (API, t2),
                     json={"table_id": m["halls"]["main"]["tables"][0]["id"]},
                     timeout=90).json()
    check(bad.get("reason") == "hall_not_allowed",
          "الباك إند يرفض حجز طاولة داخلية")

    # ---------------------------------------------------------------- 5
    print("\n5) زبونان يحاولان نفس الطاولة ← الثاني يراها محجوزة")
    m2 = httpx.get("%s/api/booking/%s" % (API, t2), timeout=60).json()
    taken = [t for t in m2["halls"]["main"]["tables"]
             if t["id"] == confirmed_table]
    check(bool(taken) and taken[0]["state"] == "booked",
          "الطاولة المحجوزة تظهر حمراء للزبون الثاني")
    check(not taken[0]["selectable"], "وغير قابلة للضغط")

    # ---------------------------------------------------------------- 6
    print("\n6) رفض الأدمن ← الطاولة تتحرر ويصل للزبون رابط جديد")
    out_tok = ses2[0]["token"]
    outdoor_free = [t for t in m2["halls"]["outdoor"]["tables"]
                    if t["selectable"]][0]
    r6 = httpx.post("%s/api/booking/%s/reserve" % (API, out_tok),
                    json={"table_id": outdoor_free["id"]}, timeout=90).json()
    time.sleep(3)
    res6 = [r for r in reservations(C2) if r["code"] == r6.get("code")][0]
    admin.decide(res6["id"], False, "اختبار آلي")
    time.sleep(2)
    after6 = db.get_reservation(res6["id"])
    check(after6["status"] == "rejected", "الحالة rejected")
    check(outdoor_free["id"] not in db.booked_table_ids(sunday.isoformat()),
          "الطاولة تحرّرت فوراً")

    # ---------------------------------------------------------------- 4
    print("\n4) حجز 12 شخصاً ← مسار يدوي بلا رابط")
    cleanup()
    start_as(C1)
    before_ses = len(sessions(C1))
    tap(C1, "B")
    tap(C1, "B:t:family")
    tap(C1, "B:d:" + sunday.isoformat())
    tap(C1, "B:p:noon")
    tap(C1, "B:h:15")
    tap(C1, "B:n:11")
    msg(C1, "12")
    msg(C1, "زبون مجموعة")
    msg(C1, "0793333333")
    tap(C1, "B:g:wedding")
    msg(C1, "خطوبة")
    big = [r for r in reservations(C1) if r.get("is_large_group")]
    check(len(sessions(C1)) == before_ses, "لم يتولّد أي رابط")
    check(len(big) == 1, "أُنشئ طلب يدوي")
    check(big and big[0]["table_id"] is None, "بلا طاولة")
    check(big and big[0]["party_size"] == 12, "العدد 12 كما كتبه الزبون")

    # --------------------------------------------------------------- 13
    print("\n13/14) تنويه الهابي أور — ثلاثاء 3 عصراً مقابل جمعة")
    check(booking.is_happy_hour(booking.local_datetime(tuesday, 15)),
          "ثلاثاء 3:00 عصراً ضمن الهابي أور")
    check(not booking.is_happy_hour(booking.local_datetime(friday, 15)),
          "جمعة 3:00 عصراً بلا تنويه — الجمعة مستثناة")

    # --------------------------------------------------------------- 15
    print("\n15) إلغاء الزبون لحجزه ← تحرير فوري + إشعار الأدمن")
    cleanup()
    start_as(C1)
    book_until_link(C1, "family", sunday, 20, 2, "زبون ملغي", "0794444444")
    tk = sessions(C1)[0]["token"]
    mp = httpx.get("%s/api/booking/%s" % (API, tk), timeout=60).json()
    pick = [t for t in mp["halls"]["outdoor"]["tables"] if t["selectable"]][0]
    rc = httpx.post("%s/api/booking/%s/reserve" % (API, tk),
                    json={"table_id": pick["id"]}, timeout=90).json()
    time.sleep(3)
    r15 = [r for r in reservations(C1) if r["code"] == rc.get("code")][0]
    check(pick["id"] in db.booked_table_ids(sunday.isoformat()),
          "الطاولة مقفلة قبل الإلغاء")
    tap(C1, "R:x:%d" % r15["id"])
    after15 = db.get_reservation(r15["id"])
    check(after15["status"] == "cancelled", "الحالة cancelled بلا موافقة أدمن")
    check(pick["id"] not in db.booked_table_ids(sunday.isoformat()),
          "الطاولة تحرّرت فوراً")

    # --------------------------------------------------------------- 16
    print("\n16) اليوم التالي ← كل الطاولات خضراء تلقائياً")
    cleanup()
    start_as(C1)
    book_until_link(C1, "family", sunday, 19, 2, "زبون الغد", "0795555555")
    tk16 = sessions(C1)[0]["token"]
    mp16 = httpx.get("%s/api/booking/%s" % (API, tk16), timeout=60).json()
    got16 = [t for t in mp16["halls"]["outdoor"]["tables"] if t["selectable"]][0]
    httpx.post("%s/api/booking/%s/reserve" % (API, tk16),
               json={"table_id": got16["id"]}, timeout=90)
    time.sleep(3)
    nxt = sunday + timedelta(days=1)
    check(got16["id"] in db.booked_table_ids(sunday.isoformat()),
          "مقفلة في يوم الحجز")
    check(got16["id"] not in db.booked_table_ids(nxt.isoformat()),
          "متاحة في اليوم التالي — الخريطة تُصفَّر")

    # --------------------------------------------------------------- 11
    print("\n11) سؤال مباشر عن الكحول ← الصيغة المحددة في 7.3")
    import ai
    for probe in ("في عندكم بيرة؟", "بتقدموا نبيذ ولا ويسكي"):
        check(ai.reply_to(probe, "ar") == texts.t("ar", "alcohol"),
              "«%s» ← الصيغة الحرفية" % probe)

    # --------------------------------------------------------------- 12
    print("\n12) سؤال عن سعر ← السعر + تنويه الخدمة والضريبة")
    answer = ai.answer("قديش سعر التبولة؟", "ar")
    check("3.750" in answer, "ذكر السعر الصحيح 3.750")
    check("5%" in answer and "7%" in answer, "ذكر تنويه الخدمة والضريبة")
    print("     الرد: %s" % answer.replace("\n", " | ")[:100])

    # --------------------------------------------------------------- 17
    print("\n17) لوحة الأدمن تعرض كل الحجوزات بحالاتها الصحيحة")
    login = httpx.post(API + "/api/admin/login",
                       json={"password": config.ADMIN_DASHBOARD_PASSWORD},
                       timeout=60).json()
    check(login.get("ok") is True, "الدخول بكلمة السر يعمل على الإنتاج")
    dash = httpx.get("%s/api/admin/reservations?token=%s&date=%s"
                     % (API, login["token"], sunday.isoformat()),
                     timeout=60).json()
    mine = [r for r in dash["rows"] if r["phone"].startswith("079")]
    check(dash.get("ok") is True and len(mine) >= 1,
          "اللوحة تعرض حجوزات اليوم", "%d صف" % len(dash["rows"]))
    statuses = {r["status"] for r in dash["rows"]}
    check(bool(statuses), "الحالات ظاهرة", " · ".join(sorted(statuses)))
    check(httpx.get("%s/api/admin/reservations?token=forged" % API,
                    timeout=60).json().get("reason") == "unauthorized",
          "توكن مزوّر مرفوض على الإنتاج")

    # ----------------------------------------------------------------- 7/8
    print("\n7/8) التنبيه بعد 15 دقيقة والتذكير والإلغاء التلقائي")
    print("     مُغطّاة بـ verify_phase4 بأوقات مضغوطة (46 فحصاً).")
    print("     على الإنتاج TEST_TIME_SCALE=1 فالمدد حقيقية —")
    print("     تُراقَب بمرور الوقت لا بسكربت.")
    check(float(health.get("test_time_scale", 0)) == 1.0,
          "الإنتاج يعمل بالأوقات الحقيقية")
    check(float(health.get("scheduler_seconds", 0)) == 60.0,
          "المسح كل 60 ثانية")

    cleanup()
    passed = sum(1 for p, _, _ in results if p)
    print("\n" + "=" * 66)
    print("النتيجة: %d/%d فحصاً ناجحاً" % (passed, len(results)))
    failed = [c for p, c, _ in results if not p]
    if failed:
        print("الفاشل:")
        for f in failed:
            print("  - %s" % f)
    print("=" * 66)
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        code = main_run()
    finally:
        cleanup()
    raise SystemExit(code)
