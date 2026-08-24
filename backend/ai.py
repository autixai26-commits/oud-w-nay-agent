# -*- coding: utf-8 -*-
"""الأسئلة الحرة عبر OpenAI — SPEC 8.

قاعدتان لا تُترَكان للنموذج:
  * الكحول (SPEC 7.3) — يُكشف بالكلمات قبل النداء، ويُرد بالصيغة الحرفية.
  * التوصيل (SPEC 3) — رد ثابت.
النموذج لا يُسأل أصلاً في هاتين الحالتين، فلا مجال لأن يجتهد.
"""
import functools
import logging

import httpx

import config
import db
import texts
from alcohol import tokens

log = logging.getLogger(__name__)

_URL = "https://api.openai.com/v1/chat/completions"
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

MENU (the complete list — nothing else exists):
{_menu_block()}
"""


def answer(user_text: str, lang: str) -> str:
    """يعيد رد النموذج، أو الرد الثابت عند أي فشل."""
    if not config.OPENAI_API_KEY:
        return texts.t(lang, "unknown")
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(_URL,
                       headers={"Authorization": "Bearer %s" % config.OPENAI_API_KEY},
                       json={"model": config.OPENAI_MODEL,
                             "temperature": 0.3,
                             "max_tokens": 400,
                             "messages": [
                                 {"role": "system", "content": system_prompt(lang)},
                                 {"role": "user", "content": user_text}]})
        if r.status_code != 200:
            # القيد ٤: لا نطبع المفتاح ولا الترويسات، فقط رمز الحالة.
            log.error("openai رمز الحالة %s", r.status_code)
            return texts.t(lang, "unknown")
        reply = r.json()["choices"][0]["message"]["content"].strip()
        return reply or texts.t(lang, "unknown")
    except Exception as exc:  # noqa: BLE001
        log.error("openai استثناء: %s", type(exc).__name__)
        return texts.t(lang, "unknown")


def reply_to(user_text: str, lang: str) -> str:
    """نقطة الدخول: تفرض القواعد الثابتة قبل أن يرى النموذج السؤال."""
    if is_alcohol_question(user_text):
        return texts.t(lang, "alcohol")
    if is_delivery_question(user_text):
        return texts.t(lang, "no_delivery")
    return answer(user_text, lang)
