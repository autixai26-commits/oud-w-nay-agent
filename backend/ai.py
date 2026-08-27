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
# الكلام الحر يجب أن يفتح **نفس** تدفق الزر، لا أن يرتجل النموذج رداً.
# لذلك تعيد detect_intent وجهةً من وجهات الأزرار نفسها (callback_data)،
# فيمرّرها منطق المحادثة إلى handle_callback مباشرة. هذا يجعل التطابق
# مع الزر مضموناً بالبناء: لا يوجد مسار ثانٍ يمكن أن ينحرف عنه.

_HAMZA = str.maketrans("أإآىة", "اااية")
# التشكيل والتطويل يُحذفان قبل التقطيع: الشدّة ليست حرف كلمة فتقسم
# «أعدّل» إلى «أعد» و«ل» ويضيع الكشف.
_DIACRITICS = re.compile(r"[ً-ْـٰ]")


def _normalize(text: str) -> str:
    """يوحّد صور الهمزة والتاء المربوطة والألف المقصورة ويحذف التشكيل."""
    return _DIACRITICS.sub("", text or "").lower().translate(_HAMZA)


def _toks(text: str) -> set:
    return set(tokens(_normalize(text)))


def _s(*words) -> set:
    """مجموعة مطبَّعة — فلا نسرد صيغ الهمزة يدوياً."""
    return {_normalize(w) for w in words}


# ------------------------------------------------------------ المفردات
# حجز قائم يملكه الزبون: قرينة كافية وحدها.
MINE = _s("حجوزاتي", "حجزاتي", "حجزي", "موعدي", "طاولتي", "حجوزاتنا",
          "حجزنا", "موعدنا", "تبعوني", "تبعي", "mine", "my")
# اسم الحجز عامةً — يحتاج فعلاً معه.
RES = _s("حجز", "الحجز", "حجوزات", "الحجوزات", "حجزت", "حجزنا", "موعد",
         "المواعيد", "booking", "bookings", "reservation", "reservations")
VIEW = _s("اشوف", "شوف", "اشوفها", "شايف", "اعرض", "عرض", "اطلع", "وين",
          "شو", "ايش", "كم", "عندي", "see", "show", "view", "list",
          "check", "where", "what", "have")
MANAGE = _s("الغي", "إلغاء", "الغاء", "عدل", "أعدل", "تعديل", "غير",
            "غيرلي", "بدل", "أجل", "تأجيل", "cancel", "modify", "change",
            "edit", "reschedule", "postpone", "move")
# فعل أمرٍ عربي صريح موجّه للبوت — أقوى قرينة في النظام، لا لبس فيها.
# استُبعد الإنجليزي عمداً: «book» تُطابَق داخل «booking» فتقلب
# «cancel my booking» إلى طلب حجز جديد.
BOOK_VERB = _s("احجز", "احجزلي", "احجزوا", "احجزيلي", "نحجز")
BOOK = _s("احجز", "احجزلي", "رابط", "طاولة", "طاوله", "فاضية", "فاضي",
          "book", "reserve", "table", "link")
# مفردات ضعيفة: تدل على الحجز فقط إن خلت الجملة من **سؤال** عن الموقع.
# «مكان» في «بدي مكان لأربعة» حجز، وفي «وين مكانكم» موقع — الفارق أداة
# السؤال لا الكلمة، فالاستثناء يقوم عليها وحدها.
BOOK_WEAK = _s("مكان", "متاح", "متاحة", "available", "spot")
LOCATION_Q = _s("وين", "فين", "عنوان", "موقع", "خريطة", "طريق", "بتقعوا",
                "where", "address", "map", "directions", "located")
WANT = _s("بدي", "بدنا", "ابغى", "ممكن", "اعطيني", "ابعتلي", "ابعث",
          "عطيني", "رجاء", "بحب", "احب", "لو", "want", "need", "give",
          "send", "please", "can", "could", "would", "like")

# المنيو وأقسامه.
# المنيو العام: لا يذكر فئة بعينها فيتوقف عند المستوى الأول.
MENU = _s("منيو", "قائمة", "لائحة", "اطلب", "اصناف", "menu", "list")
# ذكر الفئة صراحةً ينزل إليها مباشرة بدل التوقف عند المستوى الأول.
GROUP_FOOD = _s("اكل", "طعام", "ماكولات", "وجبات", "ناكل", "food", "eat",
                "dishes", "meal", "meals")
FOOD_CAT = _s("مقبلات", "سلطات", "سلطة", "مشاوي", "مشويات", "حلويات",
              "حلو", "سمك", "باستا", "شوربة", "شوربات", "appetizers",
              "salads", "grills", "desserts", "fish", "pasta", "soup")
DRINKS = _s("مشروبات", "مشروب", "عصير", "عصائر", "قهوة", "شاي", "شراب",
            "drinks", "drink", "juice", "coffee", "tea")
SHISHA = _s("ارجيلة", "الارجيلة", "ارجيله", "شيشة", "نرجيلة", "معسل",
            "shisha", "hookah", "argeela")

# معلومات المطعم.
# «مكان» المجرّدة تعني أي مكان: «في مكان تدخين» سؤالٌ عن مرفق لا
# عن موقع المطعم. نشترط صيغة الإضافة أو أداة سؤال عن الموقع.
LOCATION = _s("وين", "فين", "مكانكم", "مكانكو", "موقع", "عنوان", "بتقعوا", "بتقعو",
              "المطعم", "وصل", "خريطة", "طريق",
              "location", "where", "address", "map", "directions")
HOURS = _s("دوام", "الدوام", "اوقات", "الاوقات", "ساعات", "بتفتحوا",
           "بتسكروا", "بتفتح", "بتسكر", "مفتوح", "مفتوحين", "متى",
           "hours", "open", "opening", "close", "closing", "when")
PHONE = _s("رقم", "تلفون", "هاتف", "اتصل", "تصل", "نتصل", "موبايل",
           "phone", "number", "call", "contact")
HAPPY = _s("هابي", "اور", "خصم", "عرض", "عروض", "تخفيض", "تنزيلات",
           "happy", "discount", "offer", "deal", "promotion")
INFO = _s("معلومات", "معلومة", "info", "information", "about")

# العودة للبداية.
# فعل العودة وحده يحسم النية، حتى لو ذُكرت «القائمة» بعده.
HOME_VERB = _s("رجعني", "ارجع", "رجوع", "بلش", "نبلش", "ابدا", "نبدا",
               "restart", "start", "home", "back", "reset")


# العربية تلصق السوابق واللواحق بالكلمة: «رقم» تصير «رقمكم»، و«حلويات»
# تصير «الحلويات». المطابقة بالكلمة الكاملة تفشل في هذه كلها، وسرد كل
# صورة يدوياً لا ينتهي. فنطابق بالاحتواء في الاتجاهين، بحدّ أدنى ثلاثة
# أحرف حتى لا تلتقط كلمات الوصل القصيرة ضجيجاً.
_MIN_STEM_AR = 3
# اللاتينية أضيق: «eat» بثلاثة أحرف كانت تُطابَق داخل «weather»
# فيصير سؤال الطقس طلبَ قائمة طعام.
_MIN_STEM_EN = 4


def _min_stem(word: str) -> int:
    return _MIN_STEM_EN if word.isascii() else _MIN_STEM_AR


EXISTS = _s("فيه", "في", "عندكم", "عندك", "متوفر", "متوفرة", "باقي")


def _hit(t: set, words: set) -> bool:
    if t & words:
        return True
    for tok in t:
        if len(tok) < _MIN_STEM_AR:
            continue
        for w in words:
            if len(w) < _min_stem(w):
                continue
            # اتجاه واحد فقط: مفردةُ القاموس داخل رمز الزبون. العكس
            # يجعل رمزاً قصيراً مثل can يطابق change فينقلب المعنى.
            if w in tok:
                return True
    return False


def detect_intent(text: str):
    """يعيد وجهة زر (callback_data) أو None إن كان الكلام سؤالاً حراً.

    الترتيب مقصود: الأخصّ أولاً. «وين حجزي» حجزٌ لا موقعُ مطعم،
    و«شو عندكم مقبلات» منيو لا سؤال عام.
    """
    t = _toks(text)
    if not t:
        return None

    mine = _hit(t, MINE)
    res = _hit(t, RES)
    view = _hit(t, VIEW)
    manage = _hit(t, MANAGE)
    book = _hit(t, BOOK)
    book_weak = _hit(t, BOOK_WEAK)
    # صيغة الوجود «فيه/في/عندكم» تقوم مقام كلمة الطلب:
    # «فيه طاولة فاضية؟» سؤالٌ عن الحجز لا استفسار عام.
    wants = _hit(t, WANT) or _hit(t, EXISTS)
    menu = _hit(t, MENU)
    food_cat = _hit(t, FOOD_CAT)
    drinks = _hit(t, DRINKS)
    shisha = _hit(t, SHISHA)

    # ------------------------------------- أولوية مطلقة: حجز جديد صريح
    # «بدي احجز حجز ثاني غير الي حجزته» فيها فعل طلب صريح وإشارة لحجز
    # سابق معاً. الفعل الصريح يحسم: لا تُقرأ كطلب اطّلاع على القائم.
    if _hit(t, BOOK_VERB):
        return "B"

    # ---------------------------------------- حجز قائم (عرض/تعديل/إلغاء)
    if mine and not (menu or food_cat or drinks):
        return "R"
    # تضييق مقصود: فعل التعديل وحده لا يكفي — يحتاج إشارة إلى حجز
    # قائم (ملكية أو اسم حجز)، أو جملة قصيرة لا تحتمل غير ذلك.
    if manage and (res or mine or len(t) <= 3):
        return "R"
    if res and view and not menu:
        return "R"
    # «what did I book» و«شو حجزت» سؤالٌ عمّا حُجز لا طلبُ حجز:
    # فعل اطّلاع بلا كلمة طلب.
    if book and view and not wants:
        return "R"

    # ------------------------------------------- العودة للبداية أولاً
    # فعل العودة يحسم النية قبل أي تفسير آخر لكلمة «القائمة».
    if _hit(t, HOME_VERB):
        return "H"

    # ------------------------------------------------------ حجز جديد
    if book and (wants or view):
        return "B"
    # المفردات الضعيفة تصير حجزاً ما لم تكن الجملة سؤالاً عن الموقع.
    # المفردة الضعيفة تحتاج رغبةً صريحة لا مجرد صيغة وجود:
    # «في مكان تدخين» سؤالٌ عن مرفق، لا طلبُ حجز.
    if book_weak and _hit(t, WANT) and not _hit(t, LOCATION_Q):
        return "B"
    if _hit(t, _s("احجز", "احجزلي", "book", "reserve")):
        return "B"
    if res and wants and not view:
        return "B"

    # -------------------------------------------------------- المنيو
    # ذكر الفئة يحتاج قرينة تصفّح: طلبٌ أو سؤالُ عرضٍ أو ذكرُ القائمة.
    # «الأكل حلال؟» سؤالٌ عن الطعام لا طلبٌ لقائمته.
    browsing = wants or view or menu
    if shisha and browsing:
        return "I:shisha_info"
    if drinks and browsing:
        return "M:g:drinks"
    if (food_cat or _hit(t, GROUP_FOOD)) and browsing:
        return "M:g:food"
    if menu:
        return "M"

    # ------------------------------------------------ معلومات المطعم
    if _hit(t, HAPPY):
        return "I:happy_hour"
    if _hit(t, PHONE):
        return "I:phone"
    if _hit(t, HOURS):
        return "I:hours"
    if _hit(t, LOCATION):
        return "I:location"
    if _hit(t, INFO):
        return "I"

    return None
