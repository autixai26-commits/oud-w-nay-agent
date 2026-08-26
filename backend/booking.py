# -*- coding: utf-8 -*-
"""منطق الحجز والتوفّر وقواعد القسم 5 من SPEC.

كل حساب يعتمد على يوم الأسبوع أو الساعة يتم بالتوقيت المحلي حصراً
(CONSTRAINTS القيد ١) عبر config.now_local و config.to_local.
"""
import secrets
import string
from datetime import date as Date, datetime, timedelta  # noqa: F401  (Date/datetime تُستعملان من main)

import config
import db

# SPEC 6.1.3 و 6.1.4 — الفترات والساعات ضمنها.
PERIODS = {
    "noon":    (13, 14, 15, 16),
    "evening": (17, 18, 19, 20),
    "late":    (21, 22, 23),
}

# SPEC 6.1.5 — شرائح عدد الأشخاص. الشريحة الأخيرة تفتح المسار اليدوي.
PARTY_CHOICES = ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10))

BOOKING_DAYS_AHEAD = 7          # SPEC 6.1.2 — اليوم وبكرا وخمسة بعدها
CODE_ALPHABET = string.ascii_uppercase + string.digits


# ------------------------------------------------------------ قواعد الأيام
def is_family_only(day: Date) -> bool:
    """الخميس والجمعة والسبت: المطعم بالكامل للعائلات — SPEC 5.3.

    يُحسب على تاريخ محلي. تمرير تاريخ UTC هنا خطأ ينزلق ليوم آخر.
    """
    return day.weekday() in config.FAMILY_ONLY_WEEKDAYS


def allowed_halls(booking_type: str, day: Date) -> tuple:
    """الصالات المسموحة لهذا النوع في هذا اليوم — SPEC 5.2 و 5.3."""
    if booking_type == "family":
        return ("outdoor", "main", "narrow")      # العائلات: كل الأيام وكل الصالات
    # شباب: الصالات الداخلية ممنوعة دائماً، والخارجية الأحد–الأربعاء فقط.
    if is_family_only(day):
        return ()
    return ("outdoor",)


def reject_reason(booking_type: str, day: Date) -> str | None:
    """يعيد مفتاح نص الرفض إن كان الاختيار ممنوعاً — SPEC 5.4 (المنع المبكر)."""
    if booking_type == "singles" and is_family_only(day):
        return "singles_family_day"
    return None


def is_happy_hour(when_local: datetime) -> bool:
    """الهابي أور 1:00–6:00 مساءً، السبت–الخميس، الجمعة مستثناة — SPEC 3."""
    if when_local.weekday() == config.HAPPY_HOUR_EXCLUDED_WEEKDAY:
        return False
    return config.HAPPY_HOUR_START_HOUR <= when_local.hour < config.HAPPY_HOUR_END_HOUR


def next_days(count: int = BOOKING_DAYS_AHEAD) -> list:
    """التواريخ المعروضة للحجز، ابتداءً من اليوم بتوقيت عمّان."""
    today = config.today_local()
    return [today + timedelta(days=i) for i in range(count)]


def local_datetime(day: Date, hour: int) -> datetime:
    """يبني الموعد بالتوقيت المحلي ثم يعيده جاهزاً للتحويل إلى UTC."""
    return datetime(day.year, day.month, day.day, hour, 0,
                    tzinfo=config.LOCAL_TZ)


def period_of(hour: int) -> str | None:
    for name, hours in PERIODS.items():
        if hour in hours:
            return name
    return None


# --------------------------------------------------------------- التوفّر
def available_tables(day: Date, party_size: int, booking_type: str) -> list:
    """الطاولات المعروضة — SPEC 5.7.

    الشروط الثلاثة: السعة تكفي، والطاولة غير مقفلة في هذا التاريخ،
    والصالة مسموحة لنوع الحجز في هذا اليوم.
    التوفّر يُحسب من الحجوزات لحظياً ولا يُخزَّن في جدول الطاولات (SPEC 5.6).
    """
    halls = allowed_halls(booking_type, day)
    if not halls:
        return []
    booked = db.booked_table_ids(day.isoformat())
    return [t for t in db.all_tables()
            if t["hall"] in halls
            and t["capacity"] >= party_size
            and t["id"] not in booked]


def hall_map(day: Date, party_size: int, booking_type: str) -> dict:
    """خريطة كل الصالات للموقع: كل طاولة وحالتها.

    الحالات: available / booked / too_small، والصالة قد تكون مقفولة كلياً
    لنوع الحجز (SPEC 5.5) فتُعرض معتّمة ولا تُضغط طاولاتها.
    """
    halls = allowed_halls(booking_type, day)
    booked = db.booked_table_ids(day.isoformat())
    out: dict = {}
    for t in db.all_tables():
        hall = out.setdefault(t["hall"], {"hall": t["hall"],
                                          "locked": t["hall"] not in halls,
                                          "tables": []})
        if t["id"] in booked:
            state = "booked"
        elif t["capacity"] < party_size:
            state = "too_small"
        else:
            state = "available"
        hall["tables"].append({
            "id": t["id"], "number": t["table_number"],
            "capacity": t["capacity"], "state": state,
            "x": float(t["pos_x"]), "y": float(t["pos_y"]),
            "selectable": state == "available" and not hall["locked"],
        })
    return out


# ------------------------------------------------------- جلسات الحجز
def _token() -> str:
    return secrets.token_urlsafe(24)


def _code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


def create_session(*, platform: str, user_id: str, booking_type: str,
                   party_size: int, day: Date, hour: int,
                   name: str, phone: str, language: str) -> dict:
    """ينشئ رابط حجز صالح 30 دقيقة لاستعمال واحد — SPEC 6.1.8."""
    when_local = local_datetime(day, hour)
    row = {
        "token": _token(), "platform": platform, "user_id": str(user_id),
        "booking_type": booking_type, "party_size": party_size,
        "reservation_date": day.isoformat(),
        "reservation_at": config.to_utc(when_local).isoformat(),
        "customer_name": name, "customer_phone": phone, "language": language,
        "expires_at": (config.now_utc()
                       + config.minutes(config.BOOKING_LINK_TTL_MIN)).isoformat(),
    }
    return db.client().table("booking_sessions").insert(row).execute().data[0]


def get_session(token: str) -> dict | None:
    rows = (db.client().table("booking_sessions").select("*")
            .eq("token", token).limit(1).execute().data)
    return rows[0] if rows else None


def session_state(session: dict | None) -> str:
    """يعيد ok أو سبب البطلان — تُستعمل رسالته في الموقع."""
    if not session:
        return "not_found"
    if session.get("used_at"):
        return "used"
    expires = datetime.fromisoformat(session["expires_at"])
    if expires <= config.now_utc():
        return "expired"
    return "ok"


def public_link(token: str) -> str:
    return "%s/index.html?t=%s" % (config.PUBLIC_WEB_URL, token)


# ------------------------------------------------------------ إنشاء الحجز
class BookingError(Exception):
    """سبب رفض إنشاء الحجز — نصّه مفتاح نص لا رسالة جاهزة."""


def create_reservation(token: str, table_id: int) -> dict:
    """ينشئ الحجز بحالة pending ويقفل الطاولة فوراً — SPEC 6.2.

    القفل الحقيقي يفرضه الفهرس الفريد الجزئي في قاعدة البيانات، فلو ضغط
    زبونان على نفس الطاولة في اللحظة نفسها يفشل الثاني هنا لا في الكود.
    """
    session = get_session(token)
    state = session_state(session)
    if state != "ok":
        raise BookingError(state)

    day = Date.fromisoformat(session["reservation_date"])
    table = next((t for t in db.all_tables() if t["id"] == table_id), None)
    if not table:
        raise BookingError("table_not_found")
    if table["hall"] not in allowed_halls(session["booking_type"], day):
        raise BookingError("hall_not_allowed")
    if table["capacity"] < session["party_size"]:
        raise BookingError("too_small")
    if table["id"] in db.booked_table_ids(day.isoformat()):
        raise BookingError("taken")

    row = {
        "code": _code(), "platform": session["platform"],
        "user_id": session["user_id"],
        "customer_name": session["customer_name"],
        "customer_phone": session["customer_phone"],
        "party_size": session["party_size"],
        "booking_type": session["booking_type"],
        "table_id": table_id,
        "reservation_date": session["reservation_date"],
        "reservation_at": session["reservation_at"],
        "status": "pending", "language": session["language"],
    }
    try:
        created = db.client().table("reservations").insert(row).execute().data[0]
    except Exception as exc:  # noqa: BLE001
        # الفهرس الفريد رفض الصف: طاولة محجوزة في نفس اليوم.
        if "uniq_table_per_day" in str(exc):
            raise BookingError("taken") from exc
        raise

    # الرابط لاستعمال واحد — يُستهلك فور نجاح الحجز.
    (db.client().table("booking_sessions")
     .update({"used_at": config.now_utc().isoformat(),
              "reservation_id": created["id"]})
     .eq("token", token).execute())
    return created


def large_group_request(*, platform: str, user_id: str, party_size: int,
                        booking_type: str, day: Date, hour: int, name: str,
                        phone: str, language: str, group_type: str = "",
                        occasion: str = "") -> dict:
    """المسار اليدوي لـ11 شخصاً فأكثر — SPEC 5.8. بلا طاولة وبلا رابط."""
    when_local = local_datetime(day, hour)
    row = {
        "code": _code(), "platform": platform, "user_id": str(user_id),
        "customer_name": name, "customer_phone": phone,
        "party_size": party_size, "booking_type": booking_type,
        "table_id": None,
        "reservation_date": day.isoformat(),
        "reservation_at": config.to_utc(when_local).isoformat(),
        "status": "pending", "language": language,
        "is_large_group": True, "group_type": group_type, "occasion": occasion,
    }
    return db.client().table("reservations").insert(row).execute().data[0]


# --------------------------------------------- الأوقات المتاحة فعلياً
def available_hours(day: Date, period: str | None = None) -> list:
    """الساعات القابلة للحجز في يوم معيّن.

    لليوم نفسه نستبعد كل ساعة مضت أو حانت الآن — عرض «1:00» والساعة
    3:55 عصراً يجعل الزبون يختار موعداً فات. المقارنة بالتوقيت المحلي
    حصراً (CONSTRAINTS القيد ١).
    """
    hours = PERIODS.get(period, ()) if period else tuple(
        h for p in PERIODS.values() for h in p)
    if day != config.today_local():
        return sorted(hours)
    now = config.now_local()
    return sorted(h for h in hours if h > now.hour)


def available_periods(day: Date) -> list:
    """الفترات التي بقي فيها وقت قابل للحجز، بترتيب اليوم."""
    return [name for name in PERIODS if available_hours(day, name)]


def bookable_days(count: int = BOOKING_DAYS_AHEAD) -> list:
    """التواريخ المعروضة، مع إسقاط اليوم إن لم يبقَ فيه وقت."""
    return [d for d in next_days(count) if available_hours(d)]
