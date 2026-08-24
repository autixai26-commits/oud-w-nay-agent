# -*- coding: utf-8 -*-
"""آلة حالات المحادثة والأزرار — المرحلة 2.

لا يوجد أي نص موجّه للزبون هنا (SPEC 8) ولا أي نداء مباشر لتليجرام
(SPEC 11) — النصوص في texts.py والإرسال عبر platform_adapter.

ترميز callback_data مختصر عمداً لأن تليجرام يحدّه بـ64 بايت:
    L:<lang>       تعيين اللغة      H              القائمة الرئيسية
    M              جذر المنيو        M:g:<group>    أقسام مجموعة
    M:c:<cat>      صفحات فئة         M:s:<sub>:<p>  أصناف صفحة فرعية
    I              معلومات المطعم    I:<key>        معلومة مفردة
    B              حجز               X              تبديل اللغة
"""
import functools
import logging

import ai
import db
import texts
from platform_adapter import MAX_OPTIONS_PER_LEVEL, User, get as get_adapter

log = logging.getLogger(__name__)

PAGE_SIZE = MAX_OPTIONS_PER_LEVEL          # 10 أصناف في الصفحة (SPEC 7.1)
GROUPS = ("food", "drinks", "shisha")
INFO_KEYS = ("location", "hours", "phone", "happy_hour", "shisha_info")
NEWLINE = "\n"


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


# --------------------------------------------------------------- الشاشات
def _screen_language(adapter, user) -> None:
    adapter.send_buttons(user, texts.t("ar", "choose_language"),
                         [(texts.AR["btn_lang_ar"], "L:ar"),
                          (texts.AR["btn_lang_en"], "L:en")])


def _screen_main(adapter, user, lang, greeting=False) -> None:
    text = texts.t(lang, "welcome" if greeting else "main_menu")
    adapter.send_buttons(user, text, [
        (texts.t(lang, "btn_menu"), "M"),
        (texts.t(lang, "btn_book"), "B"),
        (texts.t(lang, "btn_info"), "I"),
        (texts.t(lang, "btn_switch_lang"), "X"),
    ])


def _screen_menu_root(adapter, user, lang) -> None:
    adapter.send_buttons(user, texts.t(lang, "menu_root"), [
        (texts.t(lang, "btn_food"), "M:g:food"),
        (texts.t(lang, "btn_drinks"), "M:g:drinks"),
        (texts.t(lang, "btn_shisha_menu"), "M:g:shisha"),
    ], nav=[(texts.t(lang, "btn_main_menu"), "H")])


def _screen_group(adapter, user, lang, group) -> None:
    cats = _cats_of(group)
    # مجموعة بفئة واحدة (الأرجيلة) لا تحتاج مستوى زائد.
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
    # فئة بصفحة فرعية واحدة تدخل للأصناف مباشرة.
    if len(subs) == 1:
        return _screen_items(adapter, user, lang, subs[0]["slug"], 0)
    adapter.send_buttons(
        user, texts.t(lang, "pick_subcategory"),
        [(_label(s, lang), "M:s:%s:0" % s["slug"]) for s in subs],
        nav=[(texts.t(lang, "btn_back"), "M:g:%s" % cat["group"])])
    return None


def build_items_screen(lang: str, sub_slug: str, page: int):
    """يبني نص صفحة الأصناف وأزرار التنقّل. منفصل عن الإرسال ليكون قابلاً للاختبار."""
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


# --------------------------------------------------------------- التوجيه
def handle_callback(user: User, data: str, lang: str) -> None:
    adapter = get_adapter(user.platform)
    parts = data.split(":")
    head = parts[0]

    if head == "L":
        chosen = parts[1] if len(parts) > 1 and parts[1] in ("ar", "en") else "ar"
        db.save_user_state(user.platform, user.user_id,
                           language=chosen, state="main")
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
        adapter.send_buttons(user, texts.t(lang, "booking_soon"), [],
                             nav=[(texts.t(lang, "btn_main_menu"), "H")])
        return None

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


def handle_text(user: User, text: str, lang) -> None:
    adapter = get_adapter(user.platform)

    # أول تفاعل: اختيار اللغة قبل أي شيء (SPEC 8).
    if not lang:
        _screen_language(adapter, user)
        return None

    stripped = (text or "").strip()
    if stripped in ("/start", "/menu", "start"):
        _screen_main(adapter, user, lang, greeting=stripped != "/menu")
        return None

    # سؤال حر: القواعد الثابتة تُفرض داخل ai.reply_to قبل النموذج.
    adapter.send_buttons(user, ai.reply_to(stripped, lang), [],
                         nav=[(texts.t(lang, "btn_menu"), "M"),
                              (texts.t(lang, "btn_main_menu"), "H")])
    return None
