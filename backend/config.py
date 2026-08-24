# -*- coding: utf-8 -*-
"""قراءة متغيرات البيئة + دوال الوقت الموحّدة.

هذا الملف هو **المكان الوحيد** المسموح فيه بقراءة الساعة.
ممنوع استخدام datetime.now() عارية في أي ملف آخر — القيد ١ في CONSTRAINTS.md.
وكل مدة زمنية تمر عبر minutes() — القيد ٢.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import os

from dotenv import load_dotenv

# .env موجود في جذر المشروع، أي المجلد الأب لـ backend/
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# ---------------------------------------------------------------- الأسرار
# القيد ٤: لا تُطبع أي من هذه القيم في أي مكان، ولا حتى جزئياً.
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = _env("OPENAI_API_KEY")
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID")
SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")
ADMIN_SETUP_SECRET = _env("ADMIN_SETUP_SECRET")
ADMIN_DASHBOARD_PASSWORD = _env("ADMIN_DASHBOARD_PASSWORD")

# ---------------------------------------------------------- إعدادات عامة
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o")
PUBLIC_WEB_URL = _env("PUBLIC_WEB_URL").rstrip("/")
BACKEND_URL = _env("BACKEND_URL").rstrip("/")
RESTAURANT_PHONE = _env("RESTAURANT_PHONE", "0770800120")

# ------------------------------------------------------ الوقت والمنطقة الزمنية
# القيد ١: التخزين UTC، والعرض وكل حسابات القواعد بتوقيت عمّان.
TIMEZONE = _env("TIMEZONE", "Asia/Amman")
LOCAL_TZ = ZoneInfo(TIMEZONE)


def now_utc() -> datetime:
    """اللحظة الحالية بـ UTC — للتخزين في قاعدة البيانات."""
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    """اللحظة الحالية بتوقيت المطعم — لكل حسابات القواعد والعرض."""
    return datetime.now(LOCAL_TZ)


def to_local(ts: datetime) -> datetime:
    """يحوّل أي طابع زمني إلى التوقيت المحلي.

    الطابع بلا منطقة زمنية يُعتبر UTC، لأن هذا ما تخزّنه قاعدة البيانات.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(LOCAL_TZ)


def to_utc(ts: datetime) -> datetime:
    """يحوّل أي طابع زمني إلى UTC. الطابع بلا منطقة زمنية يُعتبر محلياً."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=LOCAL_TZ)
    return ts.astimezone(timezone.utc)


def today_local():
    """تاريخ اليوم بعمّان — «اليوم» في /today ولوحة الأدمن وقاعدة اليوم الكامل."""
    return now_local().date()


# ---------------------------------------------- المدد الزمنية ومعامل الاختبار
# القيد ٢: ولا رقم مدة مكتوب ثابت خارج هذا المكان، وكلها تمر بـ minutes().
try:
    TEST_TIME_SCALE = float(_env("TEST_TIME_SCALE", "1") or "1")
except ValueError:
    TEST_TIME_SCALE = 1.0
if TEST_TIME_SCALE <= 0:
    TEST_TIME_SCALE = 1.0


def minutes(n: float) -> timedelta:
    """يحوّل الدقائق لمدة، مقسومة على معامل الاختبار.

    TEST_TIME_SCALE=1  → الأوقات الحقيقية (الإنتاج).
    TEST_TIME_SCALE=60 → كل دقيقة بتصير ثانية (اختبار المرحلة 4).
    """
    return timedelta(minutes=n / TEST_TIME_SCALE)


REMINDER_BEFORE_MIN = 30        # تذكير الزبون قبل الموعد — SPEC 6.4
ATTENDANCE_ASK_AFTER_MIN = 10   # سؤال الأدمن عن الحضور بعد الموعد — SPEC 6.4
AUTO_CANCEL_AFTER_MIN = 30      # الإلغاء التلقائي بعد الموعد — SPEC 6.4
ADMIN_SECOND_ALERT_MIN = 15     # تنبيه الأدمن الثاني بلا رد — SPEC 6.3
BOOKING_LINK_TTL_MIN = 30       # صلاحية رابط الحجز — SPEC 6.1

# ------------------------------------------------------------ قواعد العمل
# SPEC 5.3 — الاثنين=0 … الخميس=3، الجمعة=4، السبت=5. تُحسب على تاريخ محلي.
FAMILY_ONLY_WEEKDAYS = {3, 4, 5}

# SPEC 3 — الهابي أور 1:00–6:00 مساءً، السبت–الخميس (الجمعة مستثناة)، بالتوقيت المحلي.
HAPPY_HOUR_START_HOUR = 13
HAPPY_HOUR_END_HOUR = 18
HAPPY_HOUR_EXCLUDED_WEEKDAY = 4   # الجمعة

# SPEC 5.6 — الحالات التي تُقفل الطاولة لبقية اليوم.
OCCUPYING_STATUSES = ("pending", "confirmed", "seated")

# SPEC 5.8 — 11 شخصاً فأكثر يذهب للمسار اليدوي.
LARGE_GROUP_MIN = 11


def secrets_status() -> dict:
    """حالة المفاتيح للتشخيص — SET أو MISSING فقط، بلا أي قيمة (القيد ٤)."""
    names = ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "ELEVENLABS_API_KEY",
             "ELEVENLABS_VOICE_ID", "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
             "ADMIN_SETUP_SECRET", "ADMIN_DASHBOARD_PASSWORD",
             "PUBLIC_WEB_URL", "BACKEND_URL")
    return {n: ("SET" if globals().get(n) else "MISSING") for n in names}


# ----------------------------------------------- قاعدة الكحول (SPEC 7.3)
# ممنوع وجود أي مشروب كحولي في قاعدة البيانات ولا في الأزرار.
# المطابقة تتم على مستوى الكلمة الكاملة لا على جزء من كلمة،
# وإلا فإن "رم" أو "جن" ستطابق كلمات بريئة مثل "كرم" أو "جنبري".
ALCOHOL_TERMS_AR = (
    "عرق", "ويسكي", "وسكي", "فودكا", "بيرة", "بيره", "نبيذ",
    "رم", "تكيلا", "جن", "شمبانيا", "براندي", "ليكور", "كحول", "خمر",
)
ALCOHOL_TERMS_EN = (
    "arak", "whisky", "whiskey", "vodka", "beer", "wine", "rum",
    "tequila", "gin", "champagne", "brandy", "liqueur", "liquor",
    "alcohol", "alcoholic", "cider", "ale", "spirits", "prosecco", "sake",
)
