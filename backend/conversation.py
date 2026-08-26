# -*- coding: utf-8 -*-
"""آلة حالات المحادثة والأزرار — المرحلتان 2 و3.

لا يوجد أي نص موجّه للزبون هنا (SPEC 8) ولا أي نداء مباشر لتليجرام
(SPEC 11) — النصوص في texts.py والإرسال عبر platform_adapter،
وقواعد الحجز في booking.py.

ترميز callback_data مختصر عمداً لأن تليجرام يحدّه بـ64 بايت:
    L:<lang>    اللغة        H              القائمة الرئيسية
    M           جذر المنيو    M:g|c|s:...    مستويات المنيو
    I           معلومات       I:<key>        معلومة مفردة
    X           تبديل اللغة   B              بدء الحجز
    B:t:<type>  نوع الحجز     B:d:<iso>      التاريخ
    B:p:<per>   الفترة        B:h:<hour>     الساعة
    B:n:<size>  عدد الأشخاص   B:g:<kind>     نوع المجموعة الكبيرة
    B:x         إلغاء العملية
"""
import functools
import logging
from datetime import date as Date

import admin
import ai
import booking
import config
import db
import texts
from platform_adapter import MAX_OPTIONS_PER_LEVEL, User, get as get_adapter

log = logging.getLogger(__name__)

PAGE_SIZE = MAX_OPTIONS_PER_LEVEL          # 10 أصناف في الصفحة (SPEC 7.1)
GROUPS = ("food", "drinks", "shisha")
INFO_KEYS = ("location", "hours", "phone", "happy_hour", "shisha_info")
NEWLINE = "\n"

# حالات انتظار إدخال نصي من الزبون.
ST_NAME = "bk_name"
ST_PHONE = "bk_phone"
ST_LG_SIZE = "bk_lg_size"
ST_LG_OCCASION = "bk_lg_occasion"


# ----------------------------------------------------------- شجرة المنيو
@functools.lru_cache(maxsize=1)
def _tree() -> dict:
    """يبني شجرة التصفّح من قاعدة البيانات مرة واحدة."""
    cats: dict = {}
    for m in db.all_menu_items():
        cat = cats.setdefault(m["category"], {
            "slug": m["category"], "group": m["menu_group"],
            "ar": m["category_ar"], "en": m["category_en"], "subs": {}})
        sub = cat["subs"].setdefault(m["subcategory"], {
            "slug": m["subcategory"], "category": m["category"],
            "ar": m["subcategory_ar"], "en": m["subcategory_en"], "items": []})
        sub["items"].append(m)
    return cats


def _cats_of(group: str) -> list:
    return [c for c in _tree().values() if c["group"] == group]


def _sub(slug: str):
    for cat in _tree().values():
        if slug in cat["subs"]:
            return cat["subs"][slug]
    return None


def _label(node: dict, lang: str) -> str:
    return node["ar"] if lang == "ar" else node["en"]


# ------------------------------------------------------------- مساعدات
def _state(user: User) -> dict:
    return db.get_user_state(user.platform, user.user_id) or {}


def _data(user: User) -> dict:
    return dict(_state(user).get("data") or {})


def _save(user: User, *, state=None, data=None) -> None:
    db.save_user_state(user.platform, user.user_id, state=state, data=data)


def _weekday_name(day: Date, lang: str) -> str:
    return texts.t(lang, "weekdays").split(",")[day.weekday()]


def _date_label(day: Date, lang: str) -> str:
    today = config.today_local()
    if day == today:
        return texts.t(lang, "btn_today")
    if (day - today).days == 1:
        return texts.t(lang, "btn_tomorrow")
    return "%s %d/%d" % (_weekday_name(day, lang), day.day, day.month)


def _hour_label(hour: int) -> str:
    """يعرض الساعة بنظام 12 كما في SPEC 6.1.4 (1:00 … 11:00)."""
    return "%d:00" % (hour - 12 if hour > 12 else hour)


def _summary(data: dict, lang: str) -> str:
    day = Date.fromisoformat(data["date"])
    kind = texts.t(lang, "kind_family" if data["type"] == "family"
                   else "kind_singles")
    return texts.t(lang, "summary_line",
                   date="%s %d/%d" % (_weekday_name(day, lang), day.day, day.month),
                   time=_hour_label(data["hour"]),
                   people=data["party"], kind=kind)


def _digits_only(text: str) -> str:
    """يحوّل الأرقام العربية إلى لاتينية ويحذف ما عداها."""
    out = []
    for ch in text or "":
        if "٠" <= ch <= "٩":
            out.append(chr(ord(ch) - 0x0660 + ord("0")))
        elif ch.isdigit():
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------- الشاشات
def _screen_language(adapter, user) -> None:
    adapter.send_buttons(user, texts.t("ar", "choose_language"),
                         [(texts.AR["btn_lang_ar"], "L:ar"),
                          (texts.AR["btn_lang_en"], "L:en")])


def _screen_main(adapter, user, lang, greeting=False) -> None:
    _save(user, state="main", data={})
    text = texts.t(lang, "welcome" if greeting else "main_menu")
    adapter.send_buttons(user, text, [
        (texts.t(lang, "btn_menu"), "M"),
        (texts.t(lang, "btn_book"), "B"),
        (texts.t(lang, "btn_my_bookings"), "R"),
        (texts.t(lang, "btn_info"), "I"),
    ])


def _screen_menu_root(adapter, user, lang) -> None:
    adapter.send_buttons(user, texts.t(lang, "menu_root"), [
        (texts.t(lang, "btn_food"), "M:g:food"),
        (texts.t(lang, "btn_drinks"), "M:g:drinks"),
        (texts.t(lang, "btn_shisha_menu"), "M:g:shisha"),
    ], nav=[(texts.t(lang, "btn_main_menu"), "H")])


def _screen_group(adapter, user, lang, group) -> None:
    cats = _cats_of(group)
    if len(cats) == 1:
        return _screen_category(adapter, user, lang, cats[0]["slug"])
    adapter.send_buttons(
        user, texts.t(lang, "pick_category"),
        [(_label(c, lang), "M:c:%s" % c["slug"]) for c in cats],
        nav=[(texts.t(lang, "btn_back"), "M")])
    return None


def _screen_category(adapter, user, lang, cat_slug) -> None:
    cat = _tree().get(cat_slug)
    if not cat:
        return _screen_menu_root(adapter, user, lang)
    subs = list(cat["subs"].values())
    if len(subs) == 1:
        return _screen_items(adapter, user, lang, subs[0]["slug"], 0)
    adapter.send_buttons(
        user, texts.t(lang, "pick_subcategory"),
        [(_label(s, lang), "M:s:%s:0" % s["slug"]) for s in subs],
        nav=[(texts.t(lang, "btn_back"), "M:g:%s" % cat["group"])])
    return None


def build_items_screen(lang: str, sub_slug: str, page: int):
    """نص صفحة الأصناف وأزرار التنقّل — منفصل عن الإرسال ليكون قابلاً للاختبار."""
    sub = _sub(sub_slug)
    if not sub:
        return None

    items = sub["items"]
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [_label(sub, lang), ""]
    for it in chunk:
        name = it["name_ar"] if lang == "ar" else it["name_en"]
        lines.append("• %s — %s" % (name, texts.price(it["price"], lang)))
    lines.append("")
    if pages > 1:
        lines.append(texts.t(lang, "page_of", page=page + 1, pages=pages))
    # SPEC 7.4: التنويه الضريبي يرافق كل عرض سعر بلا استثناء.
    lines.append(texts.t(lang, "tax_note"))

    cat = _tree()[sub["category"]]
    if len(cat["subs"]) > 1:
        back = "M:c:%s" % cat["slug"]
    else:
        back = "M:g:%s" % cat["group"]

    nav = []
    if page > 0:
        nav.append((texts.t(lang, "btn_prev"), "M:s:%s:%d" % (sub_slug, page - 1)))
    if page < pages - 1:
        nav.append((texts.t(lang, "btn_next"), "M:s:%s:%d" % (sub_slug, page + 1)))
    nav.append((texts.t(lang, "btn_back"), back))

    return {"text": NEWLINE.join(lines), "nav": nav,
            "page": page, "pages": pages, "count": len(chunk)}


def _screen_items(adapter, user, lang, sub_slug, page) -> None:
    screen = build_items_screen(lang, sub_slug, page)
    if not screen:
        return _screen_menu_root(adapter, user, lang)
    adapter.send_buttons(user, screen["text"], [], nav=screen["nav"])
    return None


def _screen_info(adapter, user, lang) -> None:
    adapter.send_buttons(user, texts.t(lang, "info_menu"), [
        (texts.t(lang, "btn_location"), "I:location"),
        (texts.t(lang, "btn_hours"), "I:hours"),
        (texts.t(lang, "btn_phone"), "I:phone"),
        (texts.t(lang, "btn_happy_hour"), "I:happy_hour"),
        (texts.t(lang, "btn_shisha"), "I:shisha_info"),
    ], nav=[(texts.t(lang, "btn_main_menu"), "H")])


# ------------------------------------------------------- شاشات الحجز
def _cancel_nav(lang):
    return [(texts.t(lang, "btn_cancel_booking"), "B:x")]


def _ask_type(adapter, user, lang) -> None:
    _save(user, state="bk_type", data={})
    adapter.send_buttons(user, texts.t(lang, "ask_booking_type"), [
        (texts.t(lang, "btn_family"), "B:t:family"),
        (texts.t(lang, "btn_singles"), "B:t:singles"),
    ], nav=_cancel_nav(lang))


def _ask_date(adapter, user, lang, data) -> None:
    _save(user, state="bk_date", data=data)
    # SPEC 6.1.2 — اليوم وبكرا وخمسة بعدها = 7 أزرار، ضمن حد العشرة.
    days = booking.next_days()
    adapter.send_buttons(
        user, texts.t(lang, "ask_date"),
        [(_date_label(d, lang), "B:d:%s" % d.isoformat()) for d in days],
        nav=_cancel_nav(lang))


def _ask_period(adapter, user, lang, data) -> None:
    _save(user, state="bk_period", data=data)
    adapter.send_buttons(user, texts.t(lang, "ask_period"), [
        (texts.t(lang, "btn_noon"), "B:p:noon"),
        (texts.t(lang, "btn_evening"), "B:p:evening"),
        (texts.t(lang, "btn_late"), "B:p:late"),
    ], nav=_cancel_nav(lang))


def _ask_hour(adapter, user, lang, data, period) -> None:
    _save(user, state="bk_hour", data=data)
    hours = booking.PERIODS.get(period, ())
    adapter.send_buttons(
        user, texts.t(lang, "ask_hour"),
        [(_hour_label(h), "B:h:%d" % h) for h in hours],
        nav=[(texts.t(lang, "btn_back"), "B:p"),
             (texts.t(lang, "btn_cancel_booking"), "B:x")])


def _ask_party(adapter, user, lang, data) -> None:
    _save(user, state="bk_party", data=data)
    buttons = [("%d–%d" % (lo, hi), "B:n:%d" % hi)
               for lo, hi in booking.PARTY_CHOICES]
    buttons.append((texts.t(lang, "btn_party_11"), "B:n:11"))
    adapter.send_buttons(user, texts.t(lang, "ask_party"), buttons,
                         nav=_cancel_nav(lang))


def _ask_name(adapter, user, lang, data) -> None:
    _save(user, state=ST_NAME, data=data)
    adapter.send_buttons(user, texts.t(lang, "ask_name"), [],
                         nav=_cancel_nav(lang))


def _ask_phone(adapter, user, lang, data) -> None:
    _save(user, state=ST_PHONE, data=data)
    adapter.send_buttons(user, texts.t(lang, "ask_phone"), [],
                         nav=_cancel_nav(lang))


def _finish_booking(adapter, user, lang, data) -> None:
    """ينشئ الجلسة ويرسل الرابط — SPEC 6.1.7 و 6.1.8."""
    day = Date.fromisoformat(data["date"])
    when_local = booking.local_datetime(day, data["hour"])

    # SPEC 6.1.7 — تنويه الهابي أور قبل الرابط.
    if booking.is_happy_hour(when_local):
        adapter.send_text(user, texts.t(lang, "happy_hour_notice"))

    session = booking.create_session(
        platform=user.platform, user_id=user.user_id,
        booking_type=data["type"], party_size=data["party"],
        day=day, hour=data["hour"], name=data["name"],
        phone=data["phone"], language=lang)

    _save(user, state="bk_await_table", data=data)
    adapter.send_link(
        user,
        texts.t(lang, "link_ready", summary=_summary(data, lang)),
        texts.t(lang, "btn_choose_table"),
        booking.public_link(session["token"]))


def _finish_large_group(adapter, user, lang, data) -> None:
    """المسار اليدوي — SPEC 5.8. لا رابط ولا اختيار طاولة."""
    day = Date.fromisoformat(data["date"])
    res = booking.large_group_request(
        platform=user.platform, user_id=user.user_id,
        party_size=data["party"], booking_type=data.get("type", "family"),
        day=day, hour=data["hour"], name=data["name"], phone=data["phone"],
        language=lang, group_type=data.get("group_type", ""),
        occasion=data.get("occasion", ""))
    admin.notify_large_group(res)
    _save(user, state="main", data={})
    adapter.send_buttons(
        user,
        texts.t(lang, "large_group_sent",
                summary=_summary(data, lang), code=res["code"]),
        [], nav=[(texts.t(lang, "btn_main_menu"), "H")])


def _ask_group_type(adapter, user, lang, data) -> None:
    _save(user, state="bk_lg_type", data=data)
    adapter.send_buttons(user, texts.t(lang, "ask_group_type"), [
        (texts.t(lang, "btn_group_family"), "B:g:family"),
        (texts.t(lang, "btn_group_wedding"), "B:g:wedding"),
        (texts.t(lang, "btn_group_singles"), "B:g:singles"),
    ], nav=_cancel_nav(lang))


# ------------------------------------------------- حجوزات الزبون (SPEC 6.5)
def _screen_my_bookings(adapter, user, lang) -> None:
    rows = db.upcoming_for_user(user.platform, user.user_id,
                                config.today_local().isoformat())
    if not rows:
        adapter.send_buttons(user, texts.t(lang, "my_bookings_empty"), [],
                             nav=[(texts.t(lang, "btn_book"), "B"),
                                  (texts.t(lang, "btn_main_menu"), "H")])
        return None

    lines = [texts.t(lang, "my_bookings_title"), ""]
    buttons = []
    # حد العشرة يشمل زري الإلغاء والتعديل لكل حجز، فنعرض أحدث أربعة.
    for res in rows[:4]:
        lines.append(texts.t(
            lang, "res_line", code=res["code"],
            date=admin._fmt_date(res, lang), time=admin._fmt_time(res),
            table=admin._table_number(res),
            status=admin._status_label(res, lang)))
        buttons.append((texts.t(lang, "btn_cancel_res", code=res["code"]),
                        "R:x:%d" % res["id"]))
        buttons.append((texts.t(lang, "btn_edit_res", code=res["code"]),
                        "R:e:%d" % res["id"]))
    adapter.send_buttons(user, NEWLINE.join(lines), buttons,
                         nav=[(texts.t(lang, "btn_main_menu"), "H")])
    return None


def _cancel_reservation(adapter, user, lang, res_id, then_rebook=False) -> None:
    """SPEC 6.5 — الإلغاء والتعديل بلا موافقة أدمن، مع إشعار الأدمن."""
    res = db.get_reservation(res_id)
    if (not res or res["user_id"] != str(user.user_id)
            or res["status"] not in ("pending", "confirmed", "seated")):
        return _screen_my_bookings(adapter, user, lang)

    db.update_reservation(res_id, status="cancelled")
    fresh = db.get_reservation(res_id) or res
    admin.notify_customer_cancelled(fresh)

    if then_rebook:
        # SPEC 6.5 — التعديل ينقل الحجز نفسه: يرث نوعه وعدد أشخاصه فلا
        # يُسأل الزبون عمّا حدّده أصلاً، ويبقى سياق التعديل قائماً حتى
        # ينتهي أو يُلغى، فلا تُفهم رسالة تالية كحجز جديد منفصل.
        adapter.send_text(user, texts.t(lang, "edit_intro"))
        return _ask_date(adapter, user, lang, {
            "type": res["booking_type"],
            "party": res["party_size"],
            "name": res["customer_name"],
            "phone": res["customer_phone"],
            "editing": res["code"],
        })
    adapter.send_buttons(user, texts.t(lang, "res_cancelled",
                                       code=res["code"]), [],
                         nav=[(texts.t(lang, "btn_book"), "B"),
                              (texts.t(lang, "btn_main_menu"), "H")])
    return None


def _handle_reservations(adapter, user, lang, parts) -> None:
    if len(parts) == 1:
        return _screen_my_bookings(adapter, user, lang)
    try:
        res_id = int(parts[2])
    except (IndexError, ValueError):
        return _screen_my_bookings(adapter, user, lang)
    if parts[1] == "x":
        return _cancel_reservation(adapter, user, lang, res_id)
    if parts[1] == "e":
        return _cancel_reservation(adapter, user, lang, res_id, then_rebook=True)
    return _screen_my_bookings(adapter, user, lang)


def _handle_admin_callback(adapter, user, lang, parts) -> None:
    """أزرار الأدمن: البت في حجز، تسجيل الحضور، تحرير الطاولة."""
    if not db.is_admin(user.platform, user.user_id):
        adapter.send_text(user, texts.t(lang, "admin_only"))
        return None
    try:
        action, res_id = parts[1], int(parts[2])
    except (IndexError, ValueError):
        return None

    who = (db.get_user_state(user.platform, user.user_id) or {}).get(
        "data", {}).get("name") or user.user_id

    if action in ("y", "n"):
        admin.decide(res_id, action == "y", who)
        return None
    if action in ("c", "s"):
        status = admin.mark_attendance(res_id, action == "c", who)
        res = db.get_reservation(res_id)
        if status == "seated":
            admin.notify_seated_options(res)
        elif status == "no_show":
            adapter.send_text(user, texts.t(
                lang, "admin_marked_noshow", table=admin._table_number(res)))
        return None
    if action == "f":
        if admin.free_table(res_id):
            res = db.get_reservation(res_id)
            adapter.send_text(user, texts.t(
                lang, "admin_table_freed", table=admin._table_number(res)))
        return None
    return None


# --------------------------------------------------------------- التوجيه
def start_booking(user: User, lang: str) -> None:
    """يبدأ تدفق الحجز من خارج الوحدة — يستعمله أمر الأدمن /book."""
    _ask_type(get_adapter(user.platform), user, lang)


def _handle_booking(adapter, user, lang, parts) -> None:
    data = _data(user)

    if len(parts) == 1:                       # B — بدء التدفق
        return _ask_type(adapter, user, lang)

    kind = parts[1]

    if kind == "x":                           # إلغاء
        _save(user, state="main", data={})
        adapter.send_buttons(user, texts.t(lang, "booking_cancelled"), [],
                             nav=[(texts.t(lang, "btn_main_menu"), "H")])
        return None

    if kind == "t" and len(parts) > 2:        # نوع الحجز
        data["type"] = "singles" if parts[2] == "singles" else "family"
        return _ask_date(adapter, user, lang, data)

    if kind == "d" and len(parts) > 2:        # التاريخ
        try:
            day = Date.fromisoformat(parts[2])
        except ValueError:
            return _ask_date(adapter, user, lang, data)
        # SPEC 5.4 — المنع المبكر: يُرفض هنا قبل توليد أي رابط.
        if booking.reject_reason(data.get("type", "family"), day):
            adapter.send_buttons(user, texts.t(lang, "singles_family_day"), [],
                                 nav=[(texts.t(lang, "btn_back"), "B:t:singles"),
                                      (texts.t(lang, "btn_main_menu"), "H")])
            return None
        data["date"] = day.isoformat()
        return _ask_period(adapter, user, lang, data)

    if kind == "p":                           # الفترة
        if len(parts) > 2 and parts[2] in booking.PERIODS:
            return _ask_hour(adapter, user, lang, data, parts[2])
        return _ask_period(adapter, user, lang, data)

    if kind == "h" and len(parts) > 2:        # الساعة
        try:
            hour = int(parts[2])
        except ValueError:
            return _ask_period(adapter, user, lang, data)
        if booking.period_of(hour) is None:
            return _ask_period(adapter, user, lang, data)
        data["hour"] = hour
        # في التعديل: العدد موروث من الحجز الأصلي، فنمضي مباشرة.
        if data.get("editing") and data.get("party"):
            if data.get("name") and data.get("phone"):
                return _finish_booking(adapter, user, lang, data)
            return _ask_name(adapter, user, lang, data)
        return _ask_party(adapter, user, lang, data)

    if kind == "n" and len(parts) > 2:        # عدد الأشخاص
        try:
            size = int(parts[2])
        except ValueError:
            return _ask_party(adapter, user, lang, data)
        if size >= config.LARGE_GROUP_MIN:
            # SPEC 5.8 — المسار اليدوي.
            data["large"] = True
            adapter.send_text(user, texts.t(lang, "large_group_intro"))
            _save(user, state=ST_LG_SIZE, data=data)
            adapter.send_buttons(user, texts.t(lang, "ask_party_exact"), [],
                                 nav=_cancel_nav(lang))
            return None
        data["party"] = size
        if data.get("editing") and data.get("name") and data.get("phone"):
            return _finish_booking(adapter, user, lang, data)
        return _ask_name(adapter, user, lang, data)

    if kind == "g" and len(parts) > 2:        # نوع المجموعة الكبيرة
        data["group_type"] = parts[2]
        _save(user, state=ST_LG_OCCASION, data=data)
        adapter.send_buttons(user, texts.t(lang, "ask_occasion"), [],
                             nav=_cancel_nav(lang))
        return None

    return _ask_type(adapter, user, lang)


def handle_callback(user: User, data: str, lang: str) -> None:
    adapter = get_adapter(user.platform)
    parts = data.split(":")
    head = parts[0]

    if head == "L":
        chosen = parts[1] if len(parts) > 1 and parts[1] in ("ar", "en") else "ar"
        db.save_user_state(user.platform, user.user_id, language=chosen)
        adapter.send_text(user, texts.t(chosen, "language_set"))
        return _screen_main(adapter, user, chosen, greeting=True)

    if head == "X":
        flipped = "en" if lang == "ar" else "ar"
        db.save_user_state(user.platform, user.user_id, language=flipped)
        adapter.send_text(user, texts.t(flipped, "language_set"))
        return _screen_main(adapter, user, flipped)

    if head == "H":
        return _screen_main(adapter, user, lang)

    if head == "I":
        if len(parts) > 1 and parts[1] in INFO_KEYS:
            adapter.send_buttons(user, texts.t(lang, parts[1]), [],
                                 nav=[(texts.t(lang, "btn_back"), "I"),
                                      (texts.t(lang, "btn_main_menu"), "H")])
            return None
        return _screen_info(adapter, user, lang)

    if head == "B":
        return _handle_booking(adapter, user, lang, parts)

    if head == "R":
        return _handle_reservations(adapter, user, lang, parts)

    if head == "A":
        return _handle_admin_callback(adapter, user, lang, parts)

    if head == "M":
        if len(parts) == 1:
            return _screen_menu_root(adapter, user, lang)
        kind = parts[1]
        if kind == "g" and len(parts) > 2 and parts[2] in GROUPS:
            return _screen_group(adapter, user, lang, parts[2])
        if kind == "c" and len(parts) > 2:
            return _screen_category(adapter, user, lang, parts[2])
        if kind == "s" and len(parts) > 3:
            try:
                page = int(parts[3])
            except ValueError:
                page = 0
            return _screen_items(adapter, user, lang, parts[2], page)
        return _screen_menu_root(adapter, user, lang)

    return _screen_main(adapter, user, lang)


def _handle_input(adapter, user, lang, state, text) -> bool:
    """يعالج الإدخال النصي أثناء تدفق الحجز. يعيد True إن استهلك الرسالة."""
    data = _data(user)
    value = (text or "").strip()

    if state == ST_NAME:
        if not value:
            _ask_name(adapter, user, lang, data)
            return True
        data["name"] = value[:80]
        _ask_phone(adapter, user, lang, data)
        return True

    if state == ST_PHONE:
        digits = _digits_only(value)
        # رقم أردني معقول: 9 أو 10 خانات. أقل من ذلك خطأ إدخال.
        if not 9 <= len(digits) <= 13:
            adapter.send_buttons(user, texts.t(lang, "invalid_phone"), [],
                                 nav=_cancel_nav(lang))
            return True
        data["phone"] = digits
        if data.get("large"):
            _ask_group_type(adapter, user, lang, data)
        else:
            _finish_booking(adapter, user, lang, data)
        return True

    if state == ST_LG_SIZE:
        digits = _digits_only(value)
        if not digits or not digits.isdigit() or int(digits) < 1:
            adapter.send_buttons(user, texts.t(lang, "invalid_number"), [],
                                 nav=_cancel_nav(lang))
            return True
        data["party"] = int(digits)
        _ask_name(adapter, user, lang, data)
        return True

    if state == ST_LG_OCCASION:
        data["occasion"] = value[:120]
        _finish_large_group(adapter, user, lang, data)
        return True

    return False


def handle_text(user: User, text: str, lang) -> None:
    adapter = get_adapter(user.platform)

    stripped = (text or "").strip()

    # الأوامر تُفحص قبل بوابة اللغة عمداً. الأدمن يسجّل نفسه بـ /admin
    # قبل أن يختار لغة، فلو سبقت البوابةُ الأمرَ لابتلعته وأعادت شاشة
    # اللغة — ولا سبيل للتسجيل إطلاقاً (SPEC 10.1 و 10.2).
    if stripped.startswith("/") and admin.handle_command(
            user, stripped, lang or texts.DEFAULT_LANG):
        return None

    # SPEC 8: شاشة اختيار اللغة أُلغيت. نكتشف اللغة من أول رسالة
    # ونبدأ بها مباشرةً، ويبقى زر التبديل في القائمة الرئيسية.
    # SPEC 8: لا زر ولا شاشة. اللغة تُكتشف من كل رسالة، وتتحوّل تلقائياً
    # متى كتب الزبون بلغة أخرى فعلاً. الرسائل القصيرة جداً لا تُبدّلها
    # حتى لا تقلبها كلمة إنجليزية عابرة داخل محادثة عربية.
    detected = texts.detect_language(stripped)
    if not lang:
        lang = detected
        db.save_user_state(user.platform, user.user_id, language=lang)
    elif detected != lang and len(stripped.split()) >= 2:
        lang = detected
        db.save_user_state(user.platform, user.user_id, language=lang)
        if stripped in ("/start", "start", ""):
            _screen_main(adapter, user, lang, greeting=True)
            return None

    if stripped in ("/start", "/menu", "start"):
        _screen_main(adapter, user, lang, greeting=stripped != "/menu")
        return None

    # إدخال ضمن تدفق الحجز له الأولوية على الأسئلة الحرة.
    if _handle_input(adapter, user, lang, _state(user).get("state"), stripped):
        return None

    # ضغطة زر تصل كرسالة نصية عادية (لوحة الرد)، فنترجم نصّها
    # إلى الإجراء المخزّن ونمرّرها لمسار الأزرار نفسه.
    action = (_data(user).get("_kb") or {}).get(stripped)
    if action:
        return handle_callback(user, action, lang)

    # SPEC 8: طلب الحجز أو التعديل نيّة لا سؤال — يبدأ التدفق المقابل
    # ولا يُمرَّر للنموذج، فالنموذج بلا أدوات يرد «لا أعرف» ويعطي الهاتف.
    # داخل تدفق حجز أو تعديل نشط، «بدي احجز يوم ثاني» تعني نقل هذا
    # الحجز لا بدء آخر من الصفر. لا نعيد التشغيل ونبقى في السياق.
    current = _state(user).get("state") or ""
    intent = ai.detect_intent(stripped)
    if current.startswith("bk_") and intent == "book":
        return _ask_date(adapter, user, lang, _data(user))
    if intent == "book":
        return _ask_type(adapter, user, lang)
    if intent == "manage":
        return _screen_my_bookings(adapter, user, lang)

    # سؤال حر: القواعد الثابتة تُفرض داخل ai.reply_to قبل النموذج.
    adapter.send_buttons(user, ai.reply_to(stripped, lang), [],
                         nav=[(texts.t(lang, "btn_menu"), "M"),
                              (texts.t(lang, "btn_main_menu"), "H")])
    return None
