# -*- coding: utf-8 -*-
"""تحقق المرحلة 1 — يقرأ من قاعدة البيانات نفسها، لا من ملفات البذرة.

    python backend/verify_phase1.py

يخرج بالرمز 1 إذا فشل أي فحص، ليصلح للاستعمال في CI لاحقاً.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import db
from alcohol import scan_items

EXPECTED_TOTAL = 26
EXPECTED_BY_HALL = {"outdoor": 11, "main": 10, "narrow": 5}
EXPECTED_SEATS = {"outdoor": 55, "main": 56, "narrow": 28}

ok = True


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("✅" if passed else "❌", line))


def main() -> int:
    print("=" * 52)
    print("تحقق المرحلة 1 — قاعدة البيانات")
    print("=" * 52)

    tables = db.all_tables()
    menu = db.all_menu_items()

    # ------------------------------------------------ 1) عدد الطاولات
    print("\n1) عدد الطاولات الإجمالي")
    check(len(tables) == EXPECTED_TOTAL,
          "الموجود %d — المطلوب %d" % (len(tables), EXPECTED_TOTAL))

    # ------------------------------------------- 2) الطاولات لكل صالة
    print("\n2) عدد الطاولات لكل صالة")
    by_hall = db.count_tables_by_hall()
    for hall, expected in EXPECTED_BY_HALL.items():
        got = by_hall.get(hall, 0)
        check(got == expected, "%-8s : %2d — المطلوب %2d" % (hall, got, expected))

    # مقاعد كل صالة (تحقق إضافي مقابل SPEC القسم 4)
    print("\n   المقاعد لكل صالة:")
    for hall, expected in EXPECTED_SEATS.items():
        got = sum(t["capacity"] for t in tables if t["hall"] == hall)
        check(got == expected, "%-8s : %3d مقعد — المطلوب %3d" % (hall, got, expected))
    total_seats = sum(t["capacity"] for t in tables)
    check(total_seats == 139, "المجموع  : %3d مقعد — المطلوب 139" % total_seats)

    # ------------------------------------------ 3) عدد أصناف المنيو
    print("\n3) عدد أصناف المنيو المحمّلة")
    print("     المجموع: %d صنف" % len(menu))
    groups: dict[str, int] = {}
    cats: dict[str, tuple[str, int]] = {}
    for m in menu:
        groups[m["menu_group"]] = groups.get(m["menu_group"], 0) + 1
        name, n = cats.get(m["category"], (m["category_ar"], 0))
        cats[m["category"]] = (name, n + 1)
    for cat, (name_ar, n) in cats.items():
        print("       %-18s %3d  %s" % (cat, n, name_ar))
    print("     حسب المجموعة: " +
          " · ".join("%s %d" % (g, n) for g, n in sorted(groups.items())))
    check(len(menu) > 0, "المنيو غير فارغ")

    # الصفحات الفرعية (SPEC 7.1) — ما تجاوز 10 يُعرض على صفحات في المرحلة 2.
    print()
    print("   الصفحات الفرعية:")
    subs: dict[str, tuple[str, int]] = {}
    for m in menu:
        name, n = subs.get(m["subcategory"], (m["subcategory_ar"], 0))
        subs[m["subcategory"]] = (name, n + 1)
    over = 0
    for sub, (name_ar, n) in subs.items():
        mark = "  ← يحتاج زر التالي" if n > 10 else ""
        over += 1 if n > 10 else 0
        print("       %-14s %3d  %s%s" % (sub, n, name_ar, mark))
    check(all(m.get("subcategory") for m in menu),
          "كل صنف له تصنيف فرعي (%d صفحة، %d منها فوق 10 خيارات)"
          % (len(subs), over))

    # ------------------------------------------- 4) قاعدة الكحول
    print("\n4) قاعدة الكحول (SPEC 7.3)")
    hard, soft = scan_items(menu)
    print("     فُحص %d صنف مقابل %d مصطلح عربي و%d إنجليزي"
          % (len(menu), len(config.ALCOHOL_TERMS_AR), len(config.ALCOHOL_TERMS_EN)))
    check(not hard, "لا يوجد أي صنف كحولي في قاعدة البيانات"
          if not hard else "وُجدت أصناف كحولية: %s"
          % ", ".join("%s (%s)" % (h["name_ar"], h["term"]) for h in hard))
    if soft:
        print("     ⚠️ تحتاج نظرة بشرية (المصطلح داخل كلمة أطول):")
        for s in soft:
            print("        %s / %s ← %s" % (s["name_ar"], s["name_en"], s["term"]))

    # ------------------------------- فحوصات سلامة إضافية على المخطط
    print("\n5) سلامة المخطط")
    check(not any(k in (tables[0] if tables else {}) for k in ("is_booked", "available", "status")),
          "جدول الطاولات لا يحوي عمود توفّر — قاعدة اليوم الكامل سليمة (SPEC 5.6)")
    nums = sorted(t["table_number"] for t in tables)
    check(len(set(nums)) == len(nums), "لا أرقام طاولات مكررة")
    check(all(0 <= float(t["pos_x"]) <= 100 and 0 <= float(t["pos_y"]) <= 100
              for t in tables), "كل إحداثيات النقاط ضمن 0–100%")

    print("\n" + "=" * 52)
    print("النتيجة: %s" % ("نجح كل الفحوصات ✅" if ok else "في فحوصات فاشلة ❌"))
    print("=" * 52)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
