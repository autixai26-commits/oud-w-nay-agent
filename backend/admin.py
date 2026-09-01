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
import slots
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
    """ردٌّ إداري: بلا لوحة أزرار الزبون (SPEC 10.2).

    محادثة الأدمن أوامرُ لا تصفّح، فلا تُعرض فيها واجهةُ الزبون. ولو
    كانت معلّقة من قبلُ تُمسح هنا.
    """
    adapter = get_adapter(user.platform)
    try:
        adapter.send_text(user, text, plain=True)
    except TypeError:                      # محوّل لا يدعم المَعلَم بعد
        adapter.send_text(user, text)


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


def _held_on(table: dict, day: Date) -> list:
    return [r for r in db.reservations_on(day.isoformat())
            if r["table_id"] == table["id"]
            and r["status"] in config.OCCUPYING_STATUSES]


def _other_day_with_booking(table: dict, day: Date):
    """أول يوم آخر في نافذة الحجز عليه حجزٌ لهذه الطاولة، أو None.

    يمنع الجواب الأخرس: «متاحة أصلاً اليوم» وعليها حجزٌ بكرا جوابٌ
    صحيح حرفياً ومضلّل عملياً. الأدمن لا يقصد يوماً لم يذكره، فالأولى
    أن يُسأل عن اليوم بدل أن يُفترض بصمت.
    """
    for candidate in booking.bookable_days():
        if candidate != day and _held_on(table, candidate):
            return candidate
    return None


def free_table_number(user: User, lang: str, numbers, day: Date | None = None):
    """تحرير طاولة أو أكثر — SPEC 5.6 و10.2. يعيد True إن تحرّر شيء.

    منفّذٌ واحد يلتقي عنده أمر السلاش والنص الحر وزر التأكيد، فلا يوجد
    منطق إداري مكرّر في ثلاثة أمكنة يفترق بينها السلوك مع الوقت.

    ولا تُخزَّن حالة في جدول الطاولات (SPEC 5.6 صراحةً): التحرير نقلُ
    الحجز إلى completed، والموقع يقرأ الحجوزات لا الطاولات — فيتحدّث
    من تلقائه في نفس اللحظة.
    """
    if isinstance(numbers, int):
        numbers = [numbers]
    day = day or config.today_local()
    label = _fmt_day(day, lang)
    _note_action(user, "free", numbers[0], day)

    freed, missing = [], []
    for number in numbers:
        table = next((t for t in db.all_tables()
                      if t["table_number"] == number), None)
        if not table:
            _reply(user, texts.t(lang, "admin_table_not_found", table=number))
            continue
        held = _held_on(table, day)
        if not held:
            missing.append((number, table))
            continue
        for res in held:
            db.update_reservation(res["id"], status="completed")
        freed.append(number)

    if freed:
        if len(freed) == 1:
            _reply(user, texts.t(lang, "admin_table_freed", table=freed[0],
                                 date=label))
        else:
            _reply(user, texts.t(lang, "admin_tables_freed", date=label,
                                 tables=" و".join(str(n) for n in freed)))

    # تُجمع الطاولات الفارغة قبل السؤال لا بعده: سؤالٌ لكل طاولة كان
    # يدهس حالةَ سابقتها، فلا يبقى معلّقاً إلا آخرها ويضيع الباقي.
    elsewhere, already = {}, []
    for number, table in missing:
        other = _other_day_with_booking(table, day)
        if other:
            elsewhere.setdefault(other, []).append(number)
        else:
            already.append(number)

    if already:
        _reply(user, texts.t(lang, "admin_table_already_free",
                             table=" و".join(str(n) for n in already),
                             date=label))
    for other, nums in elsewhere.items():
        _set_admin(user, ST_DAY, _day_tables=nums, _day_action="free",
                   _day_other=other.isoformat())
        _reply(user, texts.t(lang, "admin_maybe_other_day",
                             table=" و".join(str(n) for n in nums),
                             date=label, other=_fmt_day(other, lang)))
    return bool(freed)


ST_BLOCK_HOUR = "adm_block_hour"
ST_CLARIFY = "adm_clarify"
ST_DAY = "adm_day"
PENDING_STATES = (ST_BLOCK_HOUR, ST_CLARIFY, ST_DAY)

# منصّة الحجز الإداري ليست منصّة زبون، وهذا هو المقصود: لا صاحب له
# يُشعَر، فلا يظهر في «حجوزاتي» لأحد، ولا تلتقطه الجدولة (تتخطّى كل
# منصّة لا محوّل لها) فلا تلاحقه تذكيرات ولا أسئلة حضور ولا إلغاء
# تلقائي. أما التوفّر فيقرأ الحالة والتاريخ فقط، فيحجب الطاولة كما
# يحجبها أي حجز.
BLOCK_PLATFORM = "admin"
BLOCK_USER = "block"


def block_table(user: User, lang: str, numbers, hour: int,
                day: Date | None = None) -> bool:
    """حجز إداري لطاولة أو أكثر — SPEC 10.2.1. بلا اسم ولا هاتف."""
    if isinstance(numbers, int):
        numbers = [numbers]
    day = day or config.today_local()
    _note_action(user, "block", numbers[0], day)
    done = False
    for number in numbers:
        done = _block_one(user, lang, number, hour, day) or done
    return done


def _block_one(user: User, lang: str, number: int, hour: int,
               day: Date) -> bool:
    table = next((t for t in db.all_tables()
                  if t["table_number"] == number), None)
    if not table:
        _reply(user, texts.t(lang, "admin_table_not_found", table=number))
        return False

    if _held_on(table, day):
        _reply(user, texts.t(lang, "admin_table_taken", table=number,
                             date=_fmt_day(day, lang)))
        return False

    when = booking.local_datetime(day, hour)
    row = db.client().table("reservations").insert({
        "code": booking._code(),
        "platform": BLOCK_PLATFORM, "user_id": BLOCK_USER,
        # الاسم علامةٌ يميّزها صاحب المطعم بنظرة في /today واللوحة،
        # والهاتف شرطة لأنه لا هاتف أصلاً — لا زبون هنا.
        "customer_name": texts.t(lang, "admin_block_name"),
        "customer_phone": "—",
        "party_size": table["capacity"],
        "booking_type": "family", "table_id": table["id"],
        "reservation_date": day.isoformat(),
        "reservation_at": config.to_utc(when).isoformat(),
        "status": "confirmed", "language": lang,
    }).execute().data[0]
    _reply(user, texts.t(lang, "admin_table_blocked", table=number,
                         date=_fmt_day(day, lang), time=_fmt_time(row)))
    return True


def _fmt_day(day: Date, lang: str) -> str:
    names = texts.t(lang, "weekdays").split(",")
    return "%s %d/%d" % (names[day.weekday()], day.day, day.month)


def _admin_data(user: User) -> tuple:
    state = db.get_user_state(user.platform, user.user_id) or {}
    return state.get("state") or "", dict(state.get("data") or {})


def _set_admin(user: User, state: str, **fields) -> None:
    """يكتب حالة الأدمن وحقول سياقه؛ القيمة None تحذف الحقل."""
    _, data = _admin_data(user)
    for key, value in fields.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    db.save_user_state(user.platform, user.user_id, state=state, data=data)


def _note_action(user: User, action: str, number: int, day=None) -> None:
    """يسجّل آخر فعل إداري نُفِّذ وطاولته، ويطوي أي سؤال معلّق.

    الفعل يُسجَّل عند الشروع لا عند النجاح: «الطاولة 30 متاحة» وهي
    متاحة أصلاً تبقى إعلانَ نيّة تحرير، فترثها «وطاولة 36 كمان» صحيحةً.
    """
    _set_admin(user, "main", _admin_table=number, _last_action=action,
               _last_day=day.isoformat() if day else None,
               _block_table=None, _block_date=None, _clarify_table=None,
               _day_tables=None, _day_action=None)


def _remember_table(user: User, number) -> None:
    """يحفظ آخر طاولة ذكرها الأدمن ليُحلّ بها ضمير «عدّلها»."""
    state, _ = _admin_data(user)
    _set_admin(user, state or "main", _admin_table=number)


def _pending_block(user: User, numbers, day) -> None:
    if isinstance(numbers, int):
        numbers = [numbers]
    _set_admin(user, ST_BLOCK_HOUR, _block_table=numbers, _block_date=day,
               _clarify_table=None)


def _clear_pending_block(user: User) -> None:
    _set_admin(user, "main", _block_table=None, _block_date=None)


def handle_free_text(user: User, text: str, lang: str) -> bool:
    """تعليمات الأدمن الحرة — SPEC 10.2. يعيد True إن استهلك الرسالة.

    نقطة الفصل الوحيدة بين مسار الأدمن ومسار الزبون، وتسبق كل معالجة
    أخرى للنص. من لم يكن أدمناً لا يدخلها أصلاً، ورسالةُ الأدمن التي
    لا تحمل إشارة إدارية تخرج منها إلى مسار الزبون — فصاحب المطعم
    يبقى قادراً على تصفّح بوته وحجز طاولة فيه.
    """
    if not db.is_admin(user.platform, user.user_id):
        return False

    state, data = _admin_data(user)

    # رسالةٌ تحمل رقم طاولة أمرٌ جديد لا جوابٌ عن سؤال معلّق. لولا هذا
    # لأخذت «الطاولة 12 متاحة» جواباً عن سؤالٍ عن الطاولة 20 فحرّرت
    # الطاولة الخطأ — وهو عين الخطأ الذي أصلحناه في الحالة المعلّقة.
    fresh_command = admin_nlu.table_number(text) is not None

    # سؤال «أي يوم؟» معلّق: جوابٌ بتاريخ يُعيد تنفيذ الفعل نفسه عليه.
    if state == ST_DAY and data.get("_day_tables") and not fresh_command:
        found = slots.extract(text)
        if found.get("date"):
            day = Date.fromisoformat(found["date"])
            tables = list(data["_day_tables"])
            if data.get("_day_action") == "block":
                hour = found.get("hour") or slots.hour_from(text)
                if hour:
                    block_table(user, lang, tables, hour, day)
                else:
                    _pending_block(user, tables[0], found["date"])
                    _reply(user, texts.t(lang, "admin_ask_block_hour"))
            else:
                free_table_number(user, lang, tables, day)
            return True
        if admin_nlu.answer_to_clarify(text) in ("yes", "free"):
            other = data.get("_day_other")
            if other:
                free_table_number(user, lang, list(data["_day_tables"]),
                                  Date.fromisoformat(other))
                return True

    # سؤال الساعة معلّق: الرقم المجرّد جوابٌ عنه، والسؤال هو مرساته.
    if (state == ST_BLOCK_HOUR and data.get("_block_table")
            and not fresh_command):
        hour = slots.hour_from(text)
        if hour:
            day = data.get("_block_date")
            pending = data["_block_table"]
            block_table(user, lang,
                        pending if isinstance(pending, list) else [pending],
                        hour, Date.fromisoformat(day) if day else None)
            return True
        # ليس ساعة: إن كان أمراً إدارياً آخر نتركه يُقرأ من جديد،
        # وإلا نعيد السؤال بلا أن نتشبّث بالحالة عمياً.
        if admin_nlu.understand(text) is None:
            _reply(user, texts.t(lang, "admin_block_bad_hour"))
            return True
        _clear_pending_block(user)

    # سؤال توضيحي معلّق: التصحيح يحتفظ برقم الطاولة ولا يبدأ من الصفر.
    if (state == ST_CLARIFY and data.get("_clarify_table")
            and not fresh_command):
        number = int(data["_clarify_table"])
        pending = data.get("_clarify_tables") or [number]
        kept = data.get("_clarify_date")
        answer = admin_nlu.answer_to_clarify(text)
        found = slots.extract(text)
        when = found.get("date") or kept
        when = Date.fromisoformat(when) if when else None
        if answer in ("free", "yes"):
            free_table_number(user, lang, pending, when)
            return True
        if answer == "block":
            if found.get("hour"):
                block_table(user, lang, pending, found["hour"], when)
            else:
                _pending_block(user, pending,
                               when.isoformat() if when else None)
                _reply(user, texts.t(lang, "admin_ask_block_hour"))
            return True
        if answer == "no":
            _set_admin(user, "main", _clarify_table=None)
            _reply(user, texts.t(lang, "admin_free_cancelled"))
            return True
        # تاريخٌ وحده جواباً عن السؤال: «بكرا» تعني الطاولةَ نفسها بذاك
        # اليوم، فنمضي بها بدل أن نضيّع السؤال.
        if slots.extract(text).get("date"):
            free_table_number(
                user, lang, number,
                Date.fromisoformat(slots.extract(text)["date"]))
            return True
        _set_admin(user, "main", _clarify_table=None)

    last = data.get("_admin_table")
    verdict = admin_nlu.understand(text, last_table=last,
                                   last_action=data.get("_last_action"))
    if not verdict:
        # الحارس الأخير: مسار الأدمن لا ينزل إلى ترحيب الزبون ولا إلى
        # ردٍّ عامّ ما دام في سياق إداري قائم. جملةٌ لم تكتمل أمراً لكنها
        # تحمل شظيّةً إدارية — تاريخاً أو إيجاباً أو فعلاً — تخصّ ما
        # قبلها لا محادثةً جديدة، فنسأل توضيحاً إدارياً.
        # وهذا حارسٌ ثانٍ فوق حارس الحالة المعلّقة: التسريب الذي وقع
        # فعلاً وقع **بلا حالة معلّقة**، بعد أمرٍ نُفِّذ وانتهى.
        if (state in PENDING_STATES
                or (data.get("_last_action")
                    and admin_nlu.has_admin_fragment(text))):
            table = data.get("_admin_table")
            _reply(user, texts.t(lang, "admin_lost", table=table)
                   if table else texts.t(lang, "admin_lost_bare"))
            return True
        return False

    action, value = verdict

    if action == "free":
        numbers, day = value
        free_table_number(user, lang, numbers,
                          Date.fromisoformat(day) if day else None)
        return True

    if action == "clarify_free":
        # غامضة: نسأل بصفته أدمن، ولا نردّ عليه ردّ زبون. ونفتح حالةً
        # لأن الجواب قد يأتي نصّاً («لا احجزها») لا ضغطةَ زر.
        numbers, day = value
        first = numbers[0]
        _set_admin(user, ST_CLARIFY, _clarify_table=first,
                   _clarify_tables=numbers, _admin_table=first,
                   _clarify_date=day)
        label = (" و".join(str(n) for n in numbers) if len(numbers) > 1
                 else str(first))
        get_adapter(user.platform).send_buttons(
            user, texts.t(lang, "admin_free_confirm", table=label),
            [(texts.t(lang, "btn_admin_free_yes"), "A:t:%d" % first),
             (texts.t(lang, "btn_admin_free_no"), "A:tx:0")])
        return True

    if action == "clarify_target":
        _reply(user, texts.t(lang, "admin_which_table"))
        return True

    if action == "block":
        numbers, hour, day = value
        when = Date.fromisoformat(day) if day else None
        if hour:
            block_table(user, lang, numbers, hour, when)
            return True
        # الوقت الحقل الوحيد الناقص: سؤال واحد، ولا شيء غيره.
        _remember_table(user, numbers[0])
        _pending_block(user, numbers, day)
        _reply(user, texts.t(lang, "admin_ask_block_hour"))
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
