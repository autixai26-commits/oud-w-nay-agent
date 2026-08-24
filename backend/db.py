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


# ------------------------------------------------------- حالة المستخدم
# SPEC 11: المفتاح (platform, user_id) وليس telegram_id وحده،
# حتى تعمل نفس الجداول مع واتساب بلا هجرة.
def get_user_state(platform: str, user_id: str) -> dict | None:
    rows = (client().table("user_state").select("*")
            .eq("platform", platform).eq("user_id", str(user_id))
            .limit(1).execute().data)
    return rows[0] if rows else None


def save_user_state(platform: str, user_id: str, *, language: str | None = None,
                    state: str | None = None, data: dict | None = None) -> None:
    row = {"platform": platform, "user_id": str(user_id)}
    if language is not None:
        row["language"] = language
    if state is not None:
        row["state"] = state
    if data is not None:
        row["data"] = data
    client().table("user_state").upsert(
        row, on_conflict="platform,user_id").execute()


def get_language(platform: str, user_id: str) -> str | None:
    st = get_user_state(platform, user_id)
    return (st or {}).get("language")


# ------------------------------------------------------------ الأدمنية
# SPEC 10.1: يتسجّل الأدمن بنفسه بأمر /admin لأن البوت لا يستطيع
# مراسلة أحد برقم الهاتف. كل الإشعارات تصل لكل الأدمنية.
def all_admins() -> list[dict]:
    return (client().table("admins").select("*")
            .eq("is_active", True).execute().data)


def is_admin(platform: str, user_id: str) -> bool:
    rows = (client().table("admins").select("id")
            .eq("platform", platform).eq("user_id", str(user_id))
            .eq("is_active", True).limit(1).execute().data)
    return bool(rows)


def add_admin(platform: str, user_id: str, display_name: str = "") -> None:
    client().table("admins").upsert(
        {"platform": platform, "user_id": str(user_id),
         "display_name": display_name, "is_active": True},
        on_conflict="platform,user_id").execute()


# ------------------------------------------------------------ الحجوزات
def get_reservation(res_id: int) -> dict | None:
    rows = (client().table("reservations").select("*")
            .eq("id", res_id).limit(1).execute().data)
    return rows[0] if rows else None


def reservation_by_code(code: str) -> dict | None:
    rows = (client().table("reservations").select("*")
            .eq("code", code.upper().strip()).limit(1).execute().data)
    return rows[0] if rows else None


def update_reservation(res_id: int, **fields) -> dict | None:
    rows = (client().table("reservations").update(fields)
            .eq("id", res_id).execute().data)
    return rows[0] if rows else None


def reservations_on(day: str) -> list[dict]:
    """كل حجوزات تاريخ محلي معيّن مرتبة بالموعد — /today و/date واللوحة."""
    return (client().table("reservations").select("*")
            .eq("reservation_date", day)
            .order("reservation_at").execute().data)


def upcoming_for_user(platform: str, user_id: str, from_day: str) -> list[dict]:
    """حجوزات الزبون القادمة القابلة للإلغاء — SPEC 6.5."""
    return (client().table("reservations").select("*")
            .eq("platform", platform).eq("user_id", str(user_id))
            .gte("reservation_date", from_day)
            .in_("status", ["pending", "confirmed", "seated"])
            .order("reservation_at").execute().data)


def reservations_by_status(statuses: list[str]) -> list[dict]:
    """يُستعمل في المسح الدوري للجدولة."""
    return (client().table("reservations").select("*")
            .in_("status", statuses)
            .order("reservation_at").execute().data)
