# -*- coding: utf-8 -*-
"""إشعارات الأدمن وأوامره — SPEC 6.3 و 10.

كل الإشعارات تصل لكل الأدمنية، وأول رد يُعتمد وتتعطّل بقية الأزرار
ويظهر اسم من ردّ (SPEC 6.3.6).
"""
import logging
from datetime import date as Date

import booking
import admin_nlu
import config
import db
import telegram_api
import texts
from platform_adapter import User, get as get_adapter

log = logging.getLogger(__name__)

# أسماء الصالات تُعرض للأدمن كما تُعرض للزبون على الموقع.
HALL_NAMES = {
    "ar": {"outdoor": "الصالة الخارجية", "main": "الصالة الكبيرة",
           "narrow": "الصالة الضيقة"},
    "en": {"outdoor": "Outdoor hall", "main": "Main hall",
           "narrow": "Narrow hall"},
}


# --------------------------------------------------------------- مساعدات
def _lang_of(platform: str, user_id: str) -> str:
    return db.get_language(platform, user_id) or "ar"


def _table_of(res: dict) -> dict | None:
    if not res.get("table_id"):
        return None
    return next((t for t in db.all_tables() if t["id"] == res["table_id"]), None)


def _hall_name(res: dict, lang: str) -> str:
    tb = _table_of(res)
    return HALL_NAMES[lang].get(tb["hall"], "") if tb else "—"


def _table_number(res: dict) -> str:
    tb = _table_of(res)
    return str(tb["table_number"]) if tb else "—"


def _local(res: dict):
    return config.to_local(booking.datetime.fromisoformat(res["reservation_at"]))


def _fmt_date(res: dict, lang: str) -> str:
    day = Date.fromisoformat(res["reservation_date"])
    names = texts.t(lang, "weekdays").split(",")
    return "%s %d/%d" % (names[day.weekday()], day.day, day.month)


def _fmt_time(res: dict) -> str:
    h = _local(res).hour
    return "%d:00" % (h - 12 if h > 12 else h)


def _status_label(res: dict, lang: str) -> str:
    return texts.t(lang, "st_%s" % res["status"])


def summary(res: dict, lang: str = "ar") -> str:
    """سطر ملخّص يُستعمل في تنبيهات الأدمن."""
    return texts.t(lang, "admin_res_line",
                   time=_fmt_time(res), table=_table_number(res),
                   people=res["party_size"], name=res["customer_name"],
                   phone=res["customer_phone"],
                   status=_status_label(res, lang), code=res["code"])


def _send_to_admins(build) -> list[dict]:
    """يرسل لكل الأدمنية ويعيد معرّفات الرسائل لتعطيلها لاحقاً."""
    out = []
    for adm in db.all_admins():
        lang = _lang_of(adm["platform"], adm["user_id"])
        text, buttons = build(lang)
        res = telegram_api.send_message(
            adm["user_id"], text,
            {"inline_keyboard": [[{"text": lb, "callback_data": cb}]
                                 for lb, cb in buttons]} if buttons else None)
        msg = (res.get("result") or {}).get("message_id")
        if msg:
            out.append({"chat_id": adm["user_id"], "message_id": msg})
    return out


# ------------------------------------------------------- تسجيل الأدمن
def try_register(user: User, secret: str, display_name: str) -> str:
    """SPEC 10.1 — /admin <كلمة السر>. يعيد مفتاح نص الرد."""
    if db.is_admin(user.platform, user.user_id):
        return "admin_already"
    # مقارنة ثابتة الزمن ليست ضرورية هنا لأن السر يُستعمل مرة واحدة
    # ويُغيَّر بعد التسجيل، لكن القيد ٤ يمنع طباعته في أي حال.
    if not config.ADMIN_SETUP_SECRET or secret != config.ADMIN_SETUP_SECRET:
        log.warning("محاولة تسجيل أدمن بسر غير صحيح")
        return "admin_bad_secret"
    db.add_admin(user.platform, user.user_id, display_name)
    return "admin_registered"


# --------------------------------------------------- إشعار حجز جديد
def notify_new_reservation(res: dict) -> None:
    """SPEC 6.3.2 — إشعار لكل الأدمنية بأزرار القبول والرفض."""
    if res.get("is_large_group"):
        return notify_large_group(res)

    def build(lang):
        text = texts.t(
            lang, "admin_new_booking",
            table=_table_number(res), hall=_hall_name(res, lang),
            date=_fmt_date(res, lang), time=_fmt_time(res),
            people=res["party_size"],
            kind=texts.t(lang, "kind_family" if res["booking_type"] == "family"
                         else "kind_singles"),
            name=res["customer_name"], phone=res["customer_phone"],
            code=res["code"])
        buttons = [(texts.t(lang, "btn_admin_confirm"), "A:y:%d" % res["id"]),
                   (texts.t(lang, "btn_admin_reject"), "A:n:%d" % res["id"])]
        return text, buttons

    msgs = _send_to_admins(build)
    db.update_reservation(res["id"], admin_messages=msgs)


def notify_large_group(res: dict) -> None:
    """SPEC 5.8 — المسار اليدوي: إشعار بلا أزرار بت."""
    def build(lang):
        return texts.t(
            lang, "admin_large_group",
            people=res["party_size"], group=res.get("group_type") or "—",
            occasion=res.get("occasion") or "—",
            date=_fmt_date(res, lang), time=_fmt_time(res),
            name=res["customer_name"], phone=res["customer_phone"],
            code=res["code"]), []
    _send_to_admins(build)


def _disable_admin_buttons(res: dict, who: str, decision_key: str) -> None:
    """SPEC 6.3.6 — أول رد يُعتمد: تُعطَّل بقية الأزرار ويظهر اسم من ردّ."""
    for msg in res.get("admin_messages") or []:
        lang = "ar"
        note = texts.t(lang, "admin_decided",
                       who=who or "—", what=texts.t(lang, decision_key))
        telegram_api.edit_message_text(
            msg["chat_id"], msg["message_id"],
            summary(res, lang) + "\n\n" + note)


# ------------------------------------------------------- قرار الأدمن
def decide(res_id: int, approve: bool, who: str) -> str | None:
    """يثبّت الحجز أو يرفضه. يعيد None إذا كان محسوماً أصلاً."""
    res = db.get_reservation(res_id)
    if not res or res["status"] != "pending":
        return None

    new_status = "confirmed" if approve else "rejected"
    res = db.update_reservation(
        res_id, status=new_status, decided_by=who,
        decided_at=config.now_utc().isoformat()) or res

    _disable_admin_buttons(
        res, who, "decision_confirmed" if approve else "decision_rejected")

    lang = res.get("language") or "ar"
    cust = User(res["platform"], res["user_id"], res["user_id"])
    adapter = get_adapter(res["platform"])
    if approve:
        adapter.send_buttons(cust, texts.t(
            lang, "customer_confirmed",
            table=_table_number(res), hall=_hall_name(res, lang),
            date=_fmt_date(res, lang), time=_fmt_time(res),
            people=res["party_size"], name=res["customer_name"],
            code=res["code"]), [],
            nav=[(texts.t(lang, "btn_main_menu"), "H")])
    else:
        # SPEC 6.3.4 — الطاولة تتحرر تلقائياً بتغيّر الحالة، ونعرض رابطاً جديداً.
        adapter.send_buttons(cust, texts.t(lang, "customer_rejected"), [
            (texts.t(lang, "btn_book"), "B")],
            nav=[(texts.t(lang, "btn_main_menu"), "H")])
    return new_status


def mark_attendance(res_id: int, came: bool, who: str) -> str | None:
    """SPEC 6.4 — إجا / ما إجا."""
    res = db.get_reservation(res_id)
    if not res or res["status"] not in ("confirmed", "seated"):
        return None
    status = "seated" if came else "no_show"
    db.update_reservation(res_id, status=status, decided_by=who,
                          decided_at=config.now_utc().isoformat())
    return status


def free_table(res_id: int) -> str | None:
    """SPEC 5.6 — زر «الطاولة فضيت»: تعود متاحة فوراً في نفس اليوم."""
    res = db.get_reservation(res_id)
    if not res or res["status"] not in ("seated", "confirmed"):
        return None
    db.update_reservation(res_id, status="completed")
    return "completed"


# ------------------------------------------------ إشعارات الجدولة
def alert_no_reply(res: dict) -> None:
    """SPEC 6.3.5 — تنبيه ثانٍ بعد 15 دقيقة بلا رد."""
    def build(lang):
        return texts.t(lang, "admin_alert2", summary=summary(res, lang)), []
    _send_to_admins(build)


def ask_attendance(res: dict) -> None:
    """SPEC 6.4 — سؤال الأدمن بعد الموعد بـ10 دقائق."""
    def build(lang):
        return (texts.t(lang, "admin_attendance_ask",
                        table=_table_number(res), name=res["customer_name"],
                        phone=res["customer_phone"]),
                [(texts.t(lang, "btn_came"), "A:c:%d" % res["id"]),
                 (texts.t(lang, "btn_no_show"), "A:s:%d" % res["id"])])
    _send_to_admins(build)


def notify_auto_cancel(res: dict) -> None:
    def build(lang):
        return texts.t(lang, "auto_cancelled_admin",
                       summary=summary(res, lang)), []
    _send_to_admins(build)


def notify_customer_cancelled(res: dict) -> None:
    """SPEC 6.5 — الإلغاء لا يحتاج موافقة، لكن يصل إشعار للأدمن."""
    def build(lang):
        return texts.t(lang, "admin_customer_cancelled",
                       summary=summary(res, lang)), []
    _send_to_admins(build)


def notify_seated_options(res: dict) -> None:
    """بعد تسجيل الحضور نعرض زر «الطاولة فضيت» (SPEC 10.2)."""
    def build(lang):
        return (texts.t(lang, "admin_marked_seated", table=_table_number(res)),
                [(texts.t(lang, "btn_table_free"), "A:f:%d" % res["id"])])
    _send_to_admins(build)


# ------------------------------------------------- أوامر الأدمن (SPEC 10.2)
def _reply(user: User, text: str) -> None:
    get_adapter(user.platform).send_text(user, text)


def _list_day(user: User, lang: str, day: Date) -> None:
    rows = db.reservations_on(day.isoformat())
    rows = [r for r in rows if r["status"] not in ("cancelled", "rejected")]
    if not rows:
        return _reply(user, texts.t(lang, "admin_none"))
    lines = [texts.t(lang, "admin_today_title", date=_fmt_date(rows[0], lang))]
    lines += [summary(r, lang) for r in rows]
    _reply(user, "\n".join(lines))
    return None


def _stats(user: User, lang: str) -> None:
    day = config.today_local()
    rows = [r for r in db.reservations_on(day.isoformat())
            if r["status"] in config.OCCUPYING_STATUSES]
    tables = db.all_tables()
    busy = len({r["table_id"] for r in rows if r["table_id"]})
    total = len(tables)
    seats = sum(r["party_size"] for r in rows)
    _reply(user, texts.t(
        lang, "admin_stats",
        date="%d/%d" % (day.day, day.month), count=len(rows),
        busy=busy, total=total,
        rate=round(100 * busy / total) if total else 0, seats=seats))


def free_table_number(user: User, lang: str, number: int) -> bool:
    """تحرير طاولة برقمها — SPEC 5.6 و10.2. يعيد True إن تحرّرت فعلاً.

    منفّذٌ واحد يلتقي عنده أمر السلاش والنص الحر وزر التأكيد، فلا يوجد
    منطق إداري مكرّر في ثلاثة أمكنة يفترق بينها السلوك مع الوقت.

    ولا تُخزَّن حالة في جدول الطاولات (SPEC 5.6 صراحةً): التحرير نقلُ
    الحجز إلى completed، والموقع يقرأ الحجوزات لا الطاولات — فيتحدّث
    من تلقائه في نفس اللحظة.
    """
    table = next((t for t in db.all_tables()
                  if t["table_number"] == number), None)
    if not table:
        _reply(user, texts.t(lang, "admin_table_not_found", table=number))
        return False
    today = config.today_local().isoformat()
    held = [r for r in db.reservations_on(today)
            if r["table_id"] == table["id"]
            and r["status"] in config.OCCUPYING_STATUSES]
    if not held:
        _reply(user, texts.t(lang, "admin_table_already_free", table=number))
        return False
    for res in held:
        db.update_reservation(res["id"], status="completed")
    _reply(user, texts.t(lang, "admin_table_freed", table=number))
    return True


def _remember_table(user: User, number) -> None:
    """يحفظ آخر طاولة ذكرها الأدمن ليُحلّ بها ضمير «عدّلها»."""
    state = db.get_user_state(user.platform, user.user_id) or {}
    data = dict(state.get("data") or {})
    data["_admin_table"] = number
    db.save_user_state(user.platform, user.user_id, data=data)


def handle_free_text(user: User, text: str, lang: str) -> bool:
    """تعليمات الأدمن الحرة — SPEC 10.2. يعيد True إن استهلك الرسالة.

    نقطة الفصل الوحيدة بين مسار الأدمن ومسار الزبون، وتسبق كل معالجة
    أخرى للنص. من لم يكن أدمناً لا يدخلها أصلاً، ورسالةُ الأدمن التي
    لا تحمل إشارة إدارية تخرج منها إلى مسار الزبون — فصاحب المطعم
    يبقى قادراً على تصفّح بوته وحجز طاولة فيه.
    """
    if not db.is_admin(user.platform, user.user_id):
        return False

    state = db.get_user_state(user.platform, user.user_id) or {}
    last = (state.get("data") or {}).get("_admin_table")
    verdict = admin_nlu.understand(text, last_table=last)
    if not verdict:
        return False

    action, value = verdict

    if action == "free":
        _remember_table(user, value)
        free_table_number(user, lang, value)
        return True

    if action == "clarify_free":
        # غامضة: نسأل بصفته أدمن، ولا نردّ عليه ردّ زبون.
        _remember_table(user, value)
        get_adapter(user.platform).send_buttons(
            user, texts.t(lang, "admin_free_confirm", table=value),
            [(texts.t(lang, "btn_admin_free_yes"), "A:t:%d" % value),
             (texts.t(lang, "btn_admin_free_no"), "A:tx:0")])
        return True

    if action == "clarify_target":
        _reply(user, texts.t(lang, "admin_which_table"))
        return True

    if action == "busy_unsupported":
        _remember_table(user, value)
        _reply(user, texts.t(lang, "admin_busy_hint", table=value))
        return True

    if action == "today":
        _list_day(user, lang, config.today_local())
        return True

    if action == "stats":
        _stats(user, lang)
        return True

    if action == "cancel":
        return handle_command(user, "/cancel %s" % value, lang)

    if action == "book":
        return handle_command(user, "/book", lang)

    return False


def handle_command(user: User, text: str, lang: str) -> bool:
    """يعالج أوامر الأدمن. يعيد True إن استهلك الرسالة."""
    parts = text.split()
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # /admin متاح للجميع لأنه بوابة التسجيل نفسها (SPEC 10.1).
    if cmd == "/admin":
        _reply(user, texts.t(lang, try_register(user, arg, "")))
        return True

    admin_cmds = ("/today", "/date", "/cancel", "/edit", "/book", "/free",
                  "/stats", "/help")
    if cmd not in admin_cmds:
        return False
    if not db.is_admin(user.platform, user.user_id):
        # لا نكشف وجود الأوامر لغير الأدمن أكثر من اللازم.
        _reply(user, texts.t(lang, "admin_only"))
        return True

    if cmd == "/help":
        _reply(user, texts.t(lang, "admin_help"))
        return True

    if cmd == "/today":
        _list_day(user, lang, config.today_local())
        return True

    if cmd == "/date":
        try:
            day = Date.fromisoformat(arg)
        except ValueError:
            _reply(user, texts.t(lang, "admin_usage", usage="/date 2026-09-01"))
            return True
        _list_day(user, lang, day)
        return True

    if cmd == "/stats":
        _stats(user, lang)
        return True

    if cmd in ("/cancel", "/edit"):
        if not arg:
            _reply(user, texts.t(lang, "admin_usage",
                                 usage="%s <رمز الحجز>" % cmd))
            return True
        res = db.reservation_by_code(arg)
        if not res:
            _reply(user, texts.t(lang, "admin_not_found", code=arg.upper()))
            return True
        db.update_reservation(res["id"], status="cancelled")
        _reply(user, texts.t(lang, "admin_cancelled_ok", code=res["code"]))
        # SPEC 10.2 — كل تعديل يرسل إشعاراً للزبون تلقائياً.
        cust_lang = res.get("language") or "ar"
        get_adapter(res["platform"]).send_text(
            User(res["platform"], res["user_id"], res["user_id"]),
            texts.t(cust_lang, "res_cancelled", code=res["code"]))
        if cmd == "/edit":
            # التعديل = إلغاء + تدفق جديد، ويُجريه الأدمن بـ /book.
            _reply(user, texts.t(lang, "edit_intro"))
        return True

    if cmd == "/free":
        digits = "".join(c for c in arg if c.isdigit())
        if not digits:
            _reply(user, texts.t(lang, "admin_usage", usage="/free 12"))
            return True
        free_table_number(user, lang, int(digits))
        return True

    if cmd == "/book":
        # الحجز اليدوي يستعمل نفس تدفق أزرار الزبون (SPEC 10.2).
        import conversation
        conversation.start_booking(user, lang)
        return True

    return False
