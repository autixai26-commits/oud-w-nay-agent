# -*- coding: utf-8 -*-
"""نقطة التشغيل: FastAPI + webhook تليجرام + REST API.

المرحلة 2 تغطّي الـwebhook والمحادثة. الـREST API الخاص بالحجز
يُضاف في المرحلة 3.
"""
import hashlib
import hmac
import logging

from fastapi import BackgroundTasks, FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import admin
import booking
import config
import conversation
import db
import scheduler
import telegram_api
import texts
import voice
from platform_adapter import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# القيد ٤: httpx يسجّل رابط كل طلب على مستوى INFO، وفيه رابط مشروع
# Supabase كاملاً — وهو يظهر عندها في لوغات Render. نرفعه إلى WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

log = logging.getLogger("oud-w-nay")

app = FastAPI(title="Oud w Nay", docs_url=None, redoc_url=None)

# الموقع يُستضاف على Netlify والباك إند على Render، أي أصلان مختلفان.
# نسمح بأصل الموقع وحده متى عُرف؛ وقبل النشر (PUBLIC_WEB_URL فارغ) نسمح
# بكل الأصول لأن الواجهة لا تحمل أي سر وكل طلب محمي بتوكن الجلسة.
_origins = [config.PUBLIC_WEB_URL] if config.PUBLIC_WEB_URL else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

WEBHOOK_PATH = "/webhook/telegram"


@app.on_event("startup")
def _startup() -> None:
    """تبدأ الجدولة مع الخدمة. المسح يلتقط ما فات أثناء أي إعادة تشغيل."""
    scheduler.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    scheduler.stop()


def webhook_secret() -> str:
    """سر يُشتق من توكن البوت بدل متغيّر بيئة جديد.

    القيد ٤: هذه القيمة لا تُطبع ولا تُعاد في أي رد — تُقارن فقط.
    """
    return hashlib.sha256(
        config.TELEGRAM_BOT_TOKEN.encode("utf-8")).hexdigest()[:32]


@app.get("/health")
def health() -> dict:
    """فحص صحة — يعرض حالة المفاتيح بـ SET/MISSING فقط (القيد ٤)."""
    try:
        db.ping()
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unreachable"
    return {"status": "ok", "database": database,
            "secrets": config.secrets_status(),
            "timezone": config.TIMEZONE,
            "test_time_scale": config.TEST_TIME_SCALE,
            # بدون ffmpeg يتحوّل الرد الصوتي إلى نص بصمت، فنكشفه هنا
            # بدل أن نكتشفه من شكوى زبون (SPEC 9).
            "ffmpeg": voice.ffmpeg_ready(),
            "voice_keys": voice.available(),
            "scheduler_seconds": scheduler.interval_seconds()}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    # تليجرام يعيد المحاولة عند أي رمز غير 200، لذلك نرد 200 دائماً
    # ونتعامل مع الأخطاء داخلياً حتى لا تتكرر الرسالة على الزبون.
    if not hmac.compare_digest(x_telegram_bot_api_secret_token or "",
                               webhook_secret()):
        log.warning("رُفض طلب webhook: سر غير مطابق")
        return Response(status_code=200)

    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=200)

    try:
        _dispatch(update)
    except Exception as exc:  # noqa: BLE001
        log.exception("فشل في معالجة التحديث: %s", type(exc).__name__)
    return Response(status_code=200)


def _dispatch(update: dict) -> None:
    if "callback_query" in update:
        cq = update["callback_query"]
        frm = cq.get("from", {})
        chat = (cq.get("message") or {}).get("chat", {})
        user = User("telegram", str(frm.get("id")),
                    str(chat.get("id") or frm.get("id")))
        # إلزامي: يوقف دوران الزر عند الزبون فوراً.
        telegram_api.answer_callback_query(cq.get("id", ""))
        lang = db.get_language(user.platform, user.user_id)
        conversation.handle_callback(user, cq.get("data", ""), lang or "ar")
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    frm = msg.get("from", {})
    chat = msg.get("chat", {})
    user = User("telegram", str(frm.get("id")),
                str(chat.get("id") or frm.get("id")))

    lang = db.get_language(user.platform, user.user_id)

    # SPEC 9 — صوت داخل ← صوت خارج. النسخ يتم هنا ثم تكمل المعالجة
    # العادية بلا أي فرع خاص في منطق المحادثة.
    media = msg.get("voice") or msg.get("audio")
    if media:
        spoken = _transcribe_message(media)
        if not spoken:
            # فشل النسخ: نعتذر نصاً بدل الصمت، ولا نزعج الزبون بالتفاصيل.
            conversation.get_adapter(user.platform).send_text(
                user, texts.t(lang or "ar", "voice_failed"))
            return
        user.voice = True
        conversation.handle_text(user, spoken, lang)
        return

    conversation.handle_text(user, msg.get("text", ""), lang)


def _transcribe_message(media: dict) -> str:
    """ينزّل الرسالة الصوتية من تليجرام وينسخها نصاً."""
    info = telegram_api.get_file(media.get("file_id", ""))
    path = (info.get("result") or {}).get("file_path")
    if not path:
        return ""
    audio = telegram_api.download_file(path)
    return voice.transcribe(audio, filename=path.rsplit("/", 1)[-1])


# ------------------------------------------------------------ REST API
# يستهلكها موقع اختيار الطاولة. لا مفاتيح ولا أسرار تعبر هذه النقاط —
# التوكن وحده يعرّف الجلسة، وهو صالح 30 دقيقة ولاستعمال واحد (SPEC 6.1.8).

class ReserveBody(BaseModel):
    table_id: int


def _booking_payload(session: dict) -> dict:
    """ملخّص الحجز الذي تعرضه الصفحة — SPEC 6.2."""
    day = booking.Date.fromisoformat(session["reservation_date"])
    when_local = config.to_local(
        booking.datetime.fromisoformat(session["reservation_at"]))
    lang = session.get("language") or "ar"
    return {
        "date": session["reservation_date"],
        "weekday": texts.t(lang, "weekdays").split(",")[day.weekday()],
        "time": "%d:00" % (when_local.hour - 12 if when_local.hour > 12
                           else when_local.hour),
        "hour24": when_local.hour,
        "party_size": session["party_size"],
        "booking_type": session["booking_type"],
        "name": session["customer_name"],
        "language": lang,
    }


@app.get("/api/booking/{token}")
def api_booking(token: str) -> dict:
    """حالة الرابط وخريطة الصالات الثلاث."""
    session = booking.get_session(token)
    state = booking.session_state(session)
    if state != "ok":
        return {"state": state}
    day = booking.Date.fromisoformat(session["reservation_date"])
    return {
        "state": "ok",
        "booking": _booking_payload(session),
        "halls": booking.hall_map(day, session["party_size"],
                                  session["booking_type"]),
    }


def _notify_pending(platform: str, user_id: str, lang: str) -> None:
    """SPEC 6.3.1 — يطمئن الزبون في البوت بعد اختياره الطاولة."""
    try:
        conversation.get_adapter(platform).send_text(
            User(platform, user_id, user_id), texts.t(lang, "booking_pending"))
    except Exception:  # noqa: BLE001
        log.warning("تعذّر إبلاغ الزبون في البوت")


@app.post("/api/booking/{token}/reserve")
def api_reserve(token: str, body: ReserveBody,
                tasks: BackgroundTasks) -> dict:
    """ينشئ الحجز ويقفل الطاولة فوراً — SPEC 6.2.

    إشعار البوت يُنفَّذ في الخلفية عمداً: نداء Telegram API نداء شبكة
    خارجي، ولو انتظرناه لبقي متصفح الزبون معلّقاً على شاشة التأكيد
    بينما الحجز صار مثبّتاً أصلاً في قاعدة البيانات.
    """
    try:
        created = booking.create_reservation(token, body.table_id)
    except booking.BookingError as exc:
        return {"ok": False, "reason": str(exc)}

    # اللغة تأتي من صف الحجز نفسه لا من استعلام جديد للجلسة —
    # كل رحلة إضافية لقاعدة البيانات تُضاف مباشرةً لزمن انتظار الزبون.
    lang = created.get("language") or "ar"
    tasks.add_task(_notify_pending, created["platform"],
                   created["user_id"], lang)
    # SPEC 6.3.2 — إشعار كل الأدمنية. في الخلفية للسبب نفسه: نداءات
    # تليجرام متعددة لا يجوز أن يقف عندها متصفح الزبون.
    tasks.add_task(admin.notify_new_reservation, created)
    return {"ok": True, "code": created["code"], "language": lang}


# ------------------------------------------------- لوحة الأدمن (SPEC 10.3)
# الصفحة تُرسل كلمة السر مرة واحدة وتستلم توكن جلسة موقّعاً.
# كلمة السر نفسها لا توجد أبداً في كود الواجهة ولا في أي رد.

DASHBOARD_TTL_HOURS = 12


class LoginBody(BaseModel):
    password: str


class PositionsBody(BaseModel):
    token: str
    positions: list


def _sign(payload: str) -> str:
    return hmac.new(config.ADMIN_DASHBOARD_PASSWORD.encode("utf-8"),
                    payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_dashboard_token() -> str:
    """توكن موقّع بلا حالة في الخادم: صلاحيته داخله وتوقيعه يحميه."""
    expires = int((config.now_utc().timestamp())) + DASHBOARD_TTL_HOURS * 3600
    payload = str(expires)
    return "%s.%s" % (payload, _sign(payload))


def valid_dashboard_token(token: str) -> bool:
    if not token or "." not in token or not config.ADMIN_DASHBOARD_PASSWORD:
        return False
    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    try:
        return int(payload) > config.now_utc().timestamp()
    except ValueError:
        return False


def _guard(token: str) -> bool:
    if valid_dashboard_token(token):
        return True
    log.warning("رُفض طلب لوحة: توكن غير صالح")
    return False


@app.post("/api/admin/login")
def api_admin_login(body: LoginBody) -> dict:
    """يتحقق من كلمة السر ويعيد توكن جلسة. لا يعيد كلمة السر أبداً."""
    if not config.ADMIN_DASHBOARD_PASSWORD:
        return {"ok": False}
    if not hmac.compare_digest(body.password or "",
                               config.ADMIN_DASHBOARD_PASSWORD):
        log.warning("محاولة دخول للوحة بكلمة سر غير صحيحة")
        return {"ok": False}
    return {"ok": True, "token": issue_dashboard_token(),
            "hours": DASHBOARD_TTL_HOURS}


@app.get("/api/admin/reservations")
def api_admin_reservations(token: str, date: str = "",
                           status: str = "") -> dict:
    """حجوزات تاريخ معيّن مع حالتها — عرض فقط، بلا أي تعديل (SPEC 10.3)."""
    if not _guard(token):
        return {"ok": False, "reason": "unauthorized"}

    day = date or config.today_local().isoformat()
    try:
        booking.Date.fromisoformat(day)
    except ValueError:
        return {"ok": False, "reason": "bad_date"}

    tables = {t["id"]: t for t in db.all_tables()}
    rows = []
    for r in db.reservations_on(day):
        if status and r["status"] != status:
            continue
        tb = tables.get(r["table_id"])
        rows.append({
            "code": r["code"],
            "date": r["reservation_date"],
            "time": admin._fmt_time(r),
            "table": tb["table_number"] if tb else None,
            "hall": tb["hall"] if tb else None,
            "people": r["party_size"],
            "kind": r["booking_type"],
            "name": r["customer_name"],
            "phone": r["customer_phone"],
            "status": r["status"],
            "large_group": bool(r.get("is_large_group")),
        })

    occupying = [r for r in db.reservations_on(day)
                 if r["status"] in config.OCCUPYING_STATUSES]
    busy = len({r["table_id"] for r in occupying if r["table_id"]})
    total = len(tables)
    return {
        "ok": True, "date": day, "rows": rows,
        "stats": {"count": len(occupying), "busy": busy, "total": total,
                  "rate": round(100 * busy / total) if total else 0,
                  "seats": sum(r["party_size"] for r in occupying)},
    }


@app.get("/api/admin/tables")
def api_admin_tables(token: str) -> dict:
    """كل الطاولات بإحداثياتها — تستهلكها صفحة المعايرة."""
    if not _guard(token):
        return {"ok": False, "reason": "unauthorized"}
    halls: dict = {}
    for t in db.all_tables():
        halls.setdefault(t["hall"], []).append({
            "id": t["id"], "number": t["table_number"],
            "capacity": t["capacity"],
            "x": float(t["pos_x"]), "y": float(t["pos_y"])})
    return {"ok": True, "halls": halls}


@app.post("/api/admin/tables/positions")
def api_admin_positions(body: PositionsBody) -> dict:
    """يحفظ إحداثيات النقاط بعد المعايرة — SPEC القسم 4.

    الإحداثيات نسب مئوية من أبعاد الصورة، فتصمد مع أي عرض شاشة.
    """
    if not _guard(body.token):
        return {"ok": False, "reason": "unauthorized"}
    saved = 0
    for item in body.positions or []:
        try:
            table_id = int(item["id"])
            x = round(float(item["x"]), 2)
            y = round(float(item["y"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= x <= 100 and 0 <= y <= 100):
            continue
        db.client().table("tables").update(
            {"pos_x": x, "pos_y": y}).eq("id", table_id).execute()
        saved += 1
    log.info("حُفظت إحداثيات %d طاولة", saved)
    return {"ok": True, "saved": saved}
