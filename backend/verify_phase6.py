# -*- coding: utf-8 -*-
"""تحقق المرحلة 6 — لوحة العرض وصفحة المعايرة.

    python backend/verify_phase6.py

يفحص المصادقة (SPEC 10.3): كلمة السر لا تظهر في أي رد ولا في كود
الواجهة، والتوكن موقّع ولا يُقبل معطوباً ولا منتهياً، وكل واجهة
تتطلّبه. ثم يفحص بيانات اللوحة وحفظ إحداثيات المعايرة.

يخرج بالرمز 1 عند أي فشل. الإحداثيات الأصلية تُستعاد في النهاية.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import booking   # noqa: E402
import config    # noqa: E402
import db        # noqa: E402
import main      # noqa: E402
import platform_adapter  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"
UID = "__v6__"
ok = True


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class Silent(platform_adapter.BaseAdapter):
    platform = "telegram"

    def send_text(self, user, text):
        pass

    def send_buttons(self, user, text, buttons, nav=None):
        pass

    def send_link(self, user, text, label, url):
        pass


def cleanup() -> None:
    c = db.client()
    c.table("booking_sessions").delete().eq("user_id", UID).execute()
    c.table("reservations").delete().eq("user_id", UID).execute()


def main_run() -> int:
    global ok
    print("=" * 62)
    print("تحقق المرحلة 6 — اللوحة والمعايرة")
    print("=" * 62)

    platform_adapter.ADAPTERS["telegram"] = Silent()
    client = TestClient(main.app)
    password = config.ADMIN_DASHBOARD_PASSWORD
    cleanup()

    # ------------------------------------------------- 1) المصادقة
    print("\n1) المصادقة (SPEC 10.3)")
    bad = client.post("/api/admin/login", json={"password": "wrong"}).json()
    check(bad.get("ok") is False, "كلمة سر خاطئة تُرفض")
    check("token" not in bad, "لا يُعاد توكن مع الرفض")

    good = client.post("/api/admin/login", json={"password": password}).json()
    check(good.get("ok") is True, "كلمة السر الصحيحة تُقبل")
    token = good.get("token", "")
    check(bool(token), "أُعيد توكن جلسة")
    check(password not in token, "التوكن لا يحوي كلمة السر")
    check(password not in str(good), "لا يظهر أي أثر لكلمة السر في الرد")

    # ------------------------------------------- 2) صلاحية التوكن
    print("\n2) صلاحية التوكن")
    check(main.valid_dashboard_token(token), "التوكن الصحيح يُقبل")
    check(not main.valid_dashboard_token(token[:-4] + "0000"),
          "التوكن المعدَّل يُرفض — التوقيع يحميه")
    check(not main.valid_dashboard_token(""), "التوكن الفارغ يُرفض")
    check(not main.valid_dashboard_token("999.abc"),
          "توكن بتوقيع مختلق يُرفض")
    expired = "1000000000.%s" % main._sign("1000000000")
    check(not main.valid_dashboard_token(expired),
          "توكن موقّع لكن منتهي الصلاحية يُرفض")

    # -------------------------------- 3) كل الواجهات تتطلّب توكناً
    print("\n3) كل واجهات اللوحة محمية")
    guarded = [
        ("GET", "/api/admin/reservations?token=%s"),
        ("GET", "/api/admin/tables?token=%s"),
    ]
    for method, path in guarded:
        r = client.get(path % "forged").json()
        check(r.get("ok") is False and r.get("reason") == "unauthorized",
              "%-34s يرفض توكناً مختلقاً" % path.split("?")[0])
    r = client.post("/api/admin/tables/positions",
                    json={"token": "forged", "positions": []}).json()
    check(r.get("ok") is False, "/api/admin/tables/positions يرفض المختلق")

    # ------------------------------------------- 4) بيانات اللوحة
    print("\n4) بيانات اللوحة")
    day = config.today_local()
    tables = booking.available_tables(day, 2, "family")[:2]
    db.client().table("reservations").insert([{
        "code": "V6A001", "platform": "telegram", "user_id": UID,
        "customer_name": "اختبار أ", "customer_phone": "0790000001",
        "party_size": 4, "booking_type": "family", "table_id": tables[0]["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": config.to_utc(
            booking.local_datetime(day, 19)).isoformat(),
        "status": "confirmed", "language": "ar",
    }, {
        "code": "V6B002", "platform": "telegram", "user_id": UID,
        "customer_name": "اختبار ب", "customer_phone": "0790000002",
        "party_size": 2, "booking_type": "singles", "table_id": tables[1]["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": config.to_utc(
            booking.local_datetime(day, 20)).isoformat(),
        "status": "cancelled", "language": "ar",
    }]).execute()

    data = client.get("/api/admin/reservations?token=%s" % token).json()
    check(data.get("ok") is True, "الواجهة تردّ بالتوكن الصحيح")
    codes = [r["code"] for r in data["rows"]]
    check("V6A001" in codes and "V6B002" in codes,
          "الحجوزان ظاهران (%d صف)" % len(data["rows"]))
    row = [r for r in data["rows"] if r["code"] == "V6A001"][0]
    need = ("code", "date", "time", "table", "hall", "people", "kind",
            "name", "phone", "status")
    check(all(k in row for k in need),
          "كل الأعمدة التسعة موجودة كما في SPEC 10.3")
    check(row["phone"] == "0790000001" and row["name"] == "اختبار أ",
          "الاسم والهاتف صحيحان")

    # الملغى لا يُحسب في الإشغال (SPEC 5.6 — الحالات الشاغلة فقط)
    check(data["stats"]["count"] == 1,
          "الإحصاء يعدّ الحالات الشاغلة فقط (%d)" % data["stats"]["count"])
    check(data["stats"]["total"] == 26, "إجمالي الطاولات 26")

    filtered = client.get(
        "/api/admin/reservations?token=%s&status=cancelled" % token).json()
    check([r["code"] for r in filtered["rows"]] == ["V6B002"],
          "فلتر الحالة يعمل")

    other = client.get(
        "/api/admin/reservations?token=%s&date=2030-01-01" % token).json()
    check(other["ok"] and other["rows"] == [], "فلتر التاريخ يعمل")
    check(client.get("/api/admin/reservations?token=%s&date=abc"
                     % token).json().get("reason") == "bad_date",
          "تاريخ غير صالح يُرفض")

    # ------------------------------------------------ 5) المعايرة
    print("\n5) المعايرة وحفظ الإحداثيات")
    before = {t["id"]: (float(t["pos_x"]), float(t["pos_y"]))
              for t in db.all_tables()}
    api_tables = client.get("/api/admin/tables?token=%s" % token).json()
    check(api_tables.get("ok") is True, "واجهة الطاولات تردّ")
    check(sorted(api_tables["halls"]) == ["main", "narrow", "outdoor"],
          "الصالات الثلاث موجودة")
    check(sum(len(v) for v in api_tables["halls"].values()) == 26,
          "26 طاولة بإحداثياتها")

    target = api_tables["halls"]["outdoor"][0]
    moved = client.post("/api/admin/tables/positions", json={
        "token": token,
        "positions": [{"id": target["id"], "x": 12.34, "y": 56.78}]}).json()
    check(moved.get("saved") == 1, "حُفظت نقطة واحدة")
    fresh = next(t for t in db.all_tables() if t["id"] == target["id"])
    check((float(fresh["pos_x"]), float(fresh["pos_y"])) == (12.34, 56.78),
          "الإحداثيات محفوظة فعلاً في قاعدة البيانات")

    rejected = client.post("/api/admin/tables/positions", json={
        "token": token, "positions": [
            {"id": target["id"], "x": 150, "y": 10},
            {"id": target["id"], "x": -5, "y": 10},
            {"id": target["id"], "x": "abc", "y": 10},
        ]}).json()
    check(rejected.get("saved") == 0,
          "قيم خارج 0–100 أو غير رقمية تُرفض كلها")

    # استعادة الأصل حتى لا يتأثر الموقع
    client.post("/api/admin/tables/positions", json={
        "token": token,
        "positions": [{"id": tid, "x": xy[0], "y": xy[1]}
                      for tid, xy in before.items()]})
    after = {t["id"]: (float(t["pos_x"]), float(t["pos_y"]))
             for t in db.all_tables()}
    check(after == before, "استُعيدت كل الإحداثيات الأصلية")

    # -------------------------------- 6) لا كلمة سر في كود الواجهة
    print("\n6) لا كلمة سر في كود الواجهة (SPEC 10.3)")
    for name in ("admin.html", "admin.js", "calibrate.html", "calibrate.js",
                 "config.js", "index.html", "app.js"):
        src = (WEB / name).read_text(encoding="utf-8")
        check(password not in src, "%-16s خالٍ من كلمة السر" % name)

    # -------------------------- 7) الرجوع لتليجرام بعد الحجز
    print("\n7) إعادة الزبون لتليجرام بعد اختيار الطاولة")
    app_js = (WEB / "app.js").read_text(encoding="utf-8")
    cfg_js = (WEB / "config.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    check("botUsername" in cfg_js and "Oudwnay_bot" in cfg_js,
          "يوزرنيم البوت مضبوط في config.js")
    check('id="tg-back"' in html, "زر الرجوع موجود في الصفحة")
    check("tg://resolve?domain=" in app_js, "يفتح التطبيق عبر tg://")
    check("https://t.me/" in app_js, "ومعه بديل https لمن لا يملك التطبيق")
    check(app_js.count("backToBot") >= 3,
          "نص الزر معرّف بالعربية والإنجليزية ومستعمَل")
    check("setTimeout" in app_js.split("function done(")[1][:1000],
          "محاولة فتح تلقائي بعد مهلة قصيرة")

    cleanup()
    print("\n" + "=" * 62)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = main_run()
    finally:
        cleanup()
    raise SystemExit(code)
