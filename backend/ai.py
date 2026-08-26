# -*- coding: utf-8 -*-
"""الأسئلة الحرة عبر OpenRouter — SPEC 8.

OpenRouter يوفّر واجهة متوافقة مع OpenAI، فالفرق هو base_url والمفتاح فقط.

قاعدتان لا تُترَكان للنموذج:
  * الكحول (SPEC 7.3) — يُكشف بالكلمات قبل النداء، ويُرد بالصيغة الحرفية.
  * التوصيل (SPEC 3) — رد ثابت.
النموذج لا يُسأل أصلاً في هاتين الحالتين، فلا مجال لأن يجتهد.
"""
import functools
import logging
import re

import httpx

import config
import db
import texts
from alcohol import tokens

log = logging.getLogger(__name__)

_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# كلمات تدل على سؤال مباشر عن الكحول (SPEC 7.3).
_ALCOHOL_ASK = set(config.ALCOHOL_TERMS_AR) | set(config.ALCOHOL_TERMS_EN) | {
    "مشروبات روحية", "روحية", "bar", "drinks_alcohol",
}
_DELIVERY_ASK_AR = {"توصيل", "دليفري", "ديليفري", "سفري", "طلبات"}
_DELIVERY_ASK_EN = {"delivery", "deliver", "takeaway", "takeout"}


def is_alcohol_question(text: str) -> bool:
    toks = {w.lower() for w in tokens(text)}
    return bool(toks & {w.lower() for w in _ALCOHOL_ASK})


def is_delivery_question(text: str) -> bool:
    toks = {w.lower() for w in tokens(text)}
    return bool(toks & _DELIVERY_ASK_AR) or bool(toks & _DELIVERY_ASK_EN)


@functools.lru_cache(maxsize=2)
def _menu_block() -> str:
    """المنيو كنص مضغوط ليوضع في system prompt."""
    lines, current = [], None
    for m in db.all_menu_items():
        if m["category"] != current:
            current = m["category"]
            lines.append("\n[%s / %s]" % (m["category_ar"], m["category_en"]))
        lines.append("- %s | %s | %.3f JOD"
                     % (m["name_ar"], m["name_en"], float(m["price"])))
    return "\n".join(lines)


@functools.lru_cache(maxsize=2)
def system_prompt(lang: str) -> str:
    return f"""You are فرح (Farah), the hostess of Oud w Nay (عود وناي),
a Lebanese restaurant in Fuheis, Jordan.

TONE: warm but professional, feminine, natural light Jordanian dialect when
writing Arabic. At most one or two emoji per message. Never gushing.

LANGUAGE: reply ONLY in {"Arabic" if lang == "ar" else "English"}.

RESTAURANT FACTS (the only facts you have):
- Name: عود وناي — Oud w Nay Lebanese Restaurant
- Location: Fuheis, Al-Hosan Roundabout (الفحيص، دوار الحصان)
- Phone: {config.RESTAURANT_PHONE}
- Google Maps: {texts.MAPS_URL}
- Instagram: {texts.INSTAGRAM_URL}
- Hours: every day 1:00 PM to 12:00 midnight, no weekly closing day
- Happy hour: 25% off the entire bill, Saturday through Thursday,
  1:00 PM to 6:00 PM. FRIDAY IS EXCLUDED.
- Prices exclude 5% service charge and 7% sales tax — you MUST mention this
  whenever you state any price.
- Prices are in Jordanian Dinar with three decimals, e.g. 3.250.
- NO delivery and NO takeaway. Invite the guest to visit or call.
- Three halls: outdoor (11 tables), main (10), narrow (5). 26 tables total.
- Families are welcome every day. Groups of men only ("شباب") are allowed
  in the outdoor hall Sunday–Wednesday only, and never in the indoor halls.
  Thursday, Friday and Saturday the whole restaurant is families only.

HARD RULES:
1. NEVER invent anything. If the answer is not in the facts or the menu
   below, reply exactly: "{texts.t(lang, 'unknown')}"
2. NEVER discuss alcohol. The restaurant serves none and you do not confirm
   or deny it. If asked, reply exactly: "{texts.t(lang, 'alcohol')}"
   Never raise the topic yourself.
3. Stay strictly within restaurant matters. Redirect anything else politely.
4. Do not send menu images or links to images — text only.
5. Keep replies short: three sentences at most unless listing menu items.
6. Do NOT append the phone number to answers you can already answer. Give it
   ONLY in rule 1's exact "I don't know" line, or when the guest asks for it,
   or for delivery/large-group cases. Ending a correct answer with "call us"
   makes the guest think you failed to understand.
7. If the guest asks to BOOK, get a link, or CHANGE/CANCEL a booking, that is
   handled elsewhere and never reaches you. Never tell such a guest to call.

MENU (the complete list — nothing else exists):
{_menu_block()}
"""


def _headers() -> dict:
    """ترويسات OpenRouter. القيد ٤: لا تُطبع هذه الترويسات أبداً."""
    return {"Authorization": "Bearer %s" % config.OPENROUTER_API_KEY,
            "HTTP-Referer": "https://github.com/autixai26-commits/oud-w-nay-agent",
            "X-Title": "Oud w Nay"}


def answer(user_text: str, lang: str) -> str:
    """يعيد رد النموذج، أو الرد الثابت عند أي فشل."""
    if not config.OPENROUTER_API_KEY:
        return texts.t(lang, "unknown")
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(_URL,
                       headers=_headers(),
                       json={"model": config.OPENROUTER_MODEL,
                             "temperature": 0.3,
                             "max_tokens": 400,
                             "messages": [
                                 {"role": "system", "content": system_prompt(lang)},
                                 {"role": "user", "content": user_text}]})
        if r.status_code != 200:
            # القيد ٤: لا نطبع المفتاح ولا الترويسات، فقط رمز الحالة.
            log.error("openrouter رمز الحالة %s", r.status_code)
            return texts.t(lang, "unknown")
        reply = r.json()["choices"][0]["message"]["content"].strip()
        return reply or texts.t(lang, "unknown")
    except Exception as exc:  # noqa: BLE001
        log.error("openrouter استثناء: %s", type(exc).__name__)
        return texts.t(lang, "unknown")


def reply_to(user_text: str, lang: str) -> str:
    """نقطة الدخول: تفرض القواعد الثابتة قبل أن يرى النموذج السؤال."""
    if is_alcohol_question(user_text):
        return texts.t(lang, "alcohol")
    if is_delivery_question(user_text):
        return texts.t(lang, "no_delivery")
    return answer(user_text, lang)


# --------------------------------------------------- كشف النية (SPEC 8)
# طلب الحجز أو التعديل ليس سؤالاً عن معلومة، فلا يُمرَّر للنموذج:
# النموذج لا يملك أدوات فيرد «لا أعرف» ويعطي رقم الهاتف — وهذا خطأ.
_BOOK_AR = {_n for _n in ("احجز", "أحجز", "احجزلي", "حجز", "رابط", "الرابط",
                          "طاولة", "طاوله", "موعد")}
_BOOK_EN = {"book", "booking", "reserve", "reservation", "link", "table"}

_MANAGE_AR = {"حجوزاتي", "حجزي", "الغي", "ألغي", "إلغاء", "الغاء", "الغاء",
              "عدل", "عدّل", "أعدل", "اعدل", "تعديل", "غير", "أغير", "اغير",
              "بدل", "أبدل", "ابدل", "حجوزات", "احجوزاتي"}
_MANAGE_EN = {"cancel", "modify", "change", "edit", "reschedule",
              "bookings", "my"}

# كلمات تدل على أن الجملة طلب لا استفسار.
_WANT_AR = {"بدي", "بدنا", "ابغى", "أبغى", "ممكن", "اعطيني", "أعطيني",
            "ابعتلي", "ابعث", "عطيني", "رجاء", "بحب", "احب"}
_WANT_EN = {"want", "need", "give", "send", "please", "can", "could", "id"}


_HAMZA = str.maketrans("أإآىة", "اااية")
# التشكيل والتطويل: يجب حذفها **قبل** التقطيع لا بعده، لأن الشدّة ليست
# حرف كلمة فتقسم «أعدّل» إلى «أعد» و«ل» ويضيع الكشف.
_DIACRITICS = re.compile(r"[ً-ْـٰ]")


def _normalize(text: str) -> str:
    """يوحّد صور الهمزة والألف المقصورة والتاء المربوطة ويحذف التشكيل.

    الزبون يكتب «بدي اعدل» و«بدي أعدّل» و«بدي أعدل» — وكلها نية واحدة.
    """
    return _DIACRITICS.sub("", text or "").lower().translate(_HAMZA)


def _toks(text: str) -> set:
    return set(tokens(_normalize(text)))


# نطبّع المجموعات نفسها فلا نحتاج سرد كل صيغة همزة يدوياً.
_BOOK_AR = {_normalize(w) for w in _BOOK_AR}
_MANAGE_AR = {_normalize(w) for w in _MANAGE_AR}
_WANT_AR = {_normalize(w) for w in _WANT_AR}


def detect_intent(text: str) -> str | None:
    """يعيد 'manage' أو 'book' أو None.

    الترتيب مقصود: «بدي أعدّل حجزي» فيها «حجز» و«أعدّل» معاً،
    والتعديل هو النية الحقيقية.
    """
    t = _toks(text)
    if not t:
        return None
    wants = bool(t & _WANT_AR) or bool(t & _WANT_EN)

    if (t & _MANAGE_AR) or (t & _MANAGE_EN and (t & _BOOK_EN or wants)):
        return "manage"
    if (t & _BOOK_AR or t & _BOOK_EN) and wants:
        return "book"
    # «احجز» وحدها فعل أمر صريح لا يحتاج كلمة طلب.
    if t & {"احجز", "أحجز", "احجزلي", "book", "reserve"}:
        return "book"
    return None
