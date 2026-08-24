# -*- coding: utf-8 -*-
"""يحمّل seed/tables.json و seed/menu.json إلى قاعدة البيانات.

آمن لإعادة التشغيل: upsert على table_number للطاولات وعلى name_ar للأصناف،
فلا تتضاعف الصفوف ولا تُفقد الحجوزات المرتبطة بالطاولات.

    python backend/seed_db.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import db
from alcohol import scan_items

SEED_DIR = Path(__file__).resolve().parent / "seed"


def _load(name: str) -> list[dict]:
    with open(SEED_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def seed_tables() -> int:
    rows = _load("tables.json")
    db.client().table("tables").upsert(rows, on_conflict="table_number").execute()
    return len(rows)


def seed_menu() -> int:
    rows = _load("menu.json")

    # حاجز أخير قبل الكتابة: لا يدخل أي صنف كحولي قاعدة البيانات (SPEC 7.3).
    hits, _ = scan_items(rows)
    if hits:
        raise SystemExit(
            "أُوقف التحميل: أصناف كحولية في menu.json:\n  " +
            "\n  ".join("%s (%s)" % (h["name_ar"], h["term"]) for h in hits))

    db.client().table("menu_items").upsert(rows, on_conflict="name_ar").execute()
    return len(rows)


def main() -> None:
    print("جاري التحميل إلى Supabase…")
    n_tables = seed_tables()
    print("  الطاولات : %d صف" % n_tables)
    n_menu = seed_menu()
    print("  المنيو   : %d صنف" % n_menu)
    print("تم. شغّل الآن: python backend/verify_phase1.py")


if __name__ == "__main__":
    main()
