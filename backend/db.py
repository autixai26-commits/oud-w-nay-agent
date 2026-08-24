# -*- coding: utf-8 -*-
"""الاتصال بـ Supabase والاستعلامات المشتركة.

يستخدم مفتاح service_role — لا يُستعمل هذا الملف أبداً من كود واجهة.
"""
from functools import lru_cache

from supabase import Client, create_client

import config


@lru_cache(maxsize=1)
def client() -> Client:
    """عميل Supabase واحد يُعاد استخدامه."""
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        # القيد ٤: لا نطبع المفتاح ولا جزءاً منه، فقط أنه ناقص.
        missing = [n for n in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
                   if not getattr(config, n)]
        raise RuntimeError("متغيّرات ناقصة في .env: %s" % ", ".join(missing))
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


def ping() -> bool:
    """يتحقق أن الجداول موجودة ويمكن الوصول إليها."""
    client().table("tables").select("id").limit(1).execute()
    return True


# ------------------------------------------------------------ الطاولات
def all_tables(hall: str | None = None) -> list[dict]:
    q = client().table("tables").select("*").eq("is_active", True)
    if hall:
        q = q.eq("hall", hall)
    return q.order("table_number").execute().data


def count_tables_by_hall() -> dict[str, int]:
    rows = client().table("tables").select("hall").eq("is_active", True).execute().data
    out: dict[str, int] = {}
    for r in rows:
        out[r["hall"]] = out.get(r["hall"], 0) + 1
    return out


# ------------------------------------------------------------ المنيو
def all_menu_items(menu_group: str | None = None) -> list[dict]:
    q = client().table("menu_items").select("*").eq("is_active", True)
    if menu_group:
        q = q.eq("menu_group", menu_group)
    return q.order("sort_order").execute().data


# ------------------------------------------------------------ التوفّر
def booked_table_ids(reservation_date: str) -> set[int]:
    """أرقام الطاولات المقفلة في تاريخ معيّن — SPEC 5.6 (قاعدة اليوم الكامل).

    التوفّر يُحسب من الحجوزات لحظياً، ولا يُخزَّن في جدول الطاولات إطلاقاً.
    """
    rows = (client().table("reservations")
            .select("table_id")
            .eq("reservation_date", reservation_date)
            .in_("status", list(config.OCCUPYING_STATUSES))
            .execute().data)
    return {r["table_id"] for r in rows if r["table_id"] is not None}
