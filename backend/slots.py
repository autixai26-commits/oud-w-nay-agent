# -*- coding: utf-8 -*-
"""استخراج حقول الحجز من رسالة واحدة — طبقة slot-filling.

المشكلة التي تحلّها: التدفق كان خطياً — سؤال واحد، جواب واحد. فرسالة
مثل «بكرا شخصين الساعة 4» تحمل ثلاثة حقول، كانت تُهدر كلها ويُعاد
السؤال من الصفر وكأن الزبون لم يتكلم.

البناء هو بناء detect_intent نفسه، ممتدّاً من حقل واحد إلى عدة حقول:
استخراج مُهيكل بمرساة لغوية صريحة، لا تخمين نص حر. كل حقل يحتاج مرساة
— كلمة «الساعة»، كلمة «أشخاص»، اسم يوم — والرقم المجرّد بلا مرساة لا
يملأ شيئاً. السبب أن ملء حقل بالخطأ أسوأ من تركه فارغاً: الخطأ يمضي
بالزبون إلى حجز غلط بلا أن يشعر، والفراغ يكلّفه سؤالاً واحداً.

الترتيب مقصود: تُنتزع الساعة أولاً ويُمحى موضعها من النص قبل البحث عن
العدد، وإلا لالتقط «4» في «الساعة 4» كأنه عدد الأشخاص.
"""
import re
from datetime import date as Date, timedelta

import booking
import config

# ------------------------------------------------------------ التطبيع
# نفس تطبيع ai.py حرفياً: الهمزات والتاء المربوطة والتشكيل تُوحَّد قبل
# أي مطابقة، فـ«أربعة» و«اربعه» نصّ واحد بالنسبة للأنماط.
# ملاحظة: التاء المربوطة تُطوى إلى هاء عمداً — «الساعة» و«الساعه»
# إملاءان شائعان للكلمة نفسها في الكتابة السريعة، والهمزتان المتوسطتان
# كذلك. من لم يُطوَ منها صار نمطاً يفشل أمام إملاء صحيح.
_HAMZA = str.maketrans("أإآىةؤئ", "ااايهوي")
_DIACRITICS = re.compile(r"[ً-ْـٰ]")
_TATWEEL = re.compile(r"[‏‎]")


def normalize(text: str) -> str:
    """يوحّد الهمزات والتشكيل ويحوّل الأرقام العربية إلى لاتينية."""
    out = []
    for ch in text or "":
        if "٠" <= ch <= "٩":          # ٠-٩
            out.append(chr(ord(ch) - 0x0660 + ord("0")))
        elif "۰" <= ch <= "۹":        # ۰-۹ الفارسية
            out.append(chr(ord(ch) - 0x06f0 + ord("0")))
        else:
            out.append(ch)
    body = _TATWEEL.sub("", "".join(out))
    return _DIACRITICS.sub("", body).lower().translate(_HAMZA)


def _n(word: str) -> str:
    return normalize(word)


# --------------------------------------------------------- أرقام بالكلمات
_WORDS_AR = {
    "واحد": 1, "وحده": 1, "واحده": 1,
    "اثنين": 2, "اثنان": 2, "تنين": 2, "ثنتين": 2, "اتنين": 2,
    "ثلاثه": 3, "ثلاث": 3, "تلاته": 3, "تلات": 3,
    "اربعه": 4, "اربع": 4,
    "خمسه": 5, "خمس": 5,
    "سته": 6, "ست": 6,
    "سبعه": 7, "سبع": 7,
    "ثمانيه": 8, "ثمان": 8, "تمانيه": 8, "تمن": 8, "تمانه": 8,
    "تسعه": 9, "تسع": 9,
    "عشره": 10, "عشر": 10,
    "احدعش": 11, "حداعش": 11, "احد عشر": 11,
    "اثنعش": 12, "اتنعش": 12, "اثنا عشر": 12,
}
_WORDS_EN = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "a couple": 2, "couple": 2,
}
_WORD_NUM = {_n(k): v for k, v in _WORDS_AR.items()}
_WORD_NUM.update(_WORDS_EN)

# الأطول أولاً حتى لا يبتلع «عشر» كلمةَ «عشره».
_NUM_ALT = "|".join(
    sorted((re.escape(w) for w in _WORD_NUM), key=len, reverse=True))
_ANY_NUM = r"(\d{1,2}|" + _NUM_ALT + r")"


def _num(token: str):
    token = (token or "").strip()
    if token.isdigit():
        return int(token)
    return _WORD_NUM.get(token)


# ----------------------------------------------------------- الساعة
# «على 7» مرساةُ وقت شائعة في الأردن كـ«الساعة 7». لكن «على» حرفٌ
# كثير الورود، فيُشترط أن يليه رقم لا يتبعه اسمُ أشخاص: «على 4 أشخاص»
# عددٌ لا وقت، ولو قُرئت وقتاً لابتُلع الرقم ولضاع العدد معه.
_NOT_PEOPLE = r"(?!\s*(?:اشخاص|شخص|نفر|نفرات|افراد|فرد|ناس|people|persons))"
_HOUR_ANCHORED = re.compile(
    r"(?:الساعه|ساعه|السا?عه|at|@)\s*" + _ANY_NUM
    + r"|(?:^|\s)" + _n("على") + r"\s*" + _ANY_NUM + _NOT_PEOPLE)
# لاحقة الفترة تصلح مرساةً وحدها: «4 العصر» أو «8 pm».
_HOUR_SUFFIX = re.compile(
    _ANY_NUM + r"\s*(?:pm|p\.m\.?|am|a\.m\.?|"
    r"مساء|مسا|المساء|بالمسا|الليل|بالليل|ليلا|"
    r"العصر|عصرا|بالعصر|الظهر|ظهرا|بالظهر|صباحا|الصبح)")
_AM = re.compile(r"\b(?:am|a\.m\.?|صباحا|الصبح)\b")

_PERIOD_WORDS = (
    ("noon", ("الظهر", "ظهرا", "بالظهر", "العصر", "عصرا", "بالعصر",
              "بعد الظهر", "noon", "afternoon")),
    ("evening", ("المساء", "مساء", "مسا", "بالمسا", "العشاء", "عشاء",
                 "evening", "dinner")),
    ("late", ("سهره", "السهره", "متاخر", "بالليل", "ليلا", "الليل",
              "late", "night")),
)


def _to_evening(hour):
    """يحوّل ساعة الزبون إلى ساعة المطعم (13–23).

    المطعم يفتح 1 ظهراً ويغلق منتصف الليل، فلا التباس: «الساعة 4» لا
    تعني الرابعة فجراً. أما 12 فتقع قبل الافتتاح، فنتركها فارغة ليُسأل
    عنها بدل أن نخمّن.
    """
    if hour is None:
        return None
    if 1 <= hour <= 11:
        hour += 12
    return hour if booking.period_of(hour) else None


def _hour(text: str):
    morning = _AM.search(text) is not None
    for pattern in (_HOUR_ANCHORED, _HOUR_SUFFIX):
        match = pattern.search(text)
        if not match:
            continue
        # صباحاً = خارج الدوام. يُفحص في النص كله لا في المطابقة
        # وحدها، لأن «الساعة 9 الصبح» تُلتقط بالمرساة الأمامية فتفوت
        # اللاحقة. يُعاد المدى مع None ليُمحى الرقم فلا يُقرأ عدد أشخاص.
        if morning:
            return None, match.span()
        token = next((g for g in match.groups() if g), None)
        return _to_evening(_num(token)), match.span()
    return None, None


def _period(text: str):
    for slug, words in _PERIOD_WORDS:
        for word in words:
            if _n(word) in text:
                return slug
    return None


# ------------------------------------------------------ عدد الأشخاص
_PERSON = (r"(?:اشخاص|شخص|اشخاص|نفر|نفرات|افراد|فرد|ناس|"
           r"people|persons|person|pax|guests|guest|adults)")
_PARTY_AFTER = re.compile(_ANY_NUM + r"\s*" + _PERSON)
_PARTY_BEFORE = re.compile(_PERSON + r"\s*" + _ANY_NUM)
# «for 4» و«لأربعة» و«ل4» — حرف الجر مرساةٌ كافية في سياق الحجز.
_PARTY_FOR = re.compile(
    r"(?:\bfor\s+|(?:^|\s)ل\s?)" + _ANY_NUM + r"(?:\s|$)")
_PARTY_WE = re.compile(r"(?:احنا|نحنا|نحن|we\s+are|we're)\s*" + _ANY_NUM)
# صيغ المثنّى وحدها لا لبس فيها. «اثنين» مستثناة عمداً: «الاثنين» يوم.
_PARTY_DUAL = re.compile(r"(?:شخصين|نفرين|شخصان|فردين)")
_PARTY_ALONE = re.compile(r"(?:لحالي|بحالي|لوحدي|alone|just\s+me|by\s+myself)")

MAX_PARTY = 40


def _party(text: str):
    if _PARTY_DUAL.search(text):
        return 2
    if _PARTY_ALONE.search(text):
        return 1
    for pattern in (_PARTY_AFTER, _PARTY_BEFORE, _PARTY_WE, _PARTY_FOR):
        match = pattern.search(text)
        if match:
            size = _num(match.group(1))
            if size and 1 <= size <= MAX_PARTY:
                return size
    return None


# ------------------------------------------------------------ التاريخ
_WEEKDAYS = {
    "الاثنين": 0, "الاتنين": 0, "الإثنين": 0, "monday": 0,
    "الثلاثاء": 1, "التلاتا": 1, "الثلاثا": 1, "tuesday": 1,
    "الاربعاء": 2, "الاربعا": 2, "wednesday": 2,
    "الخميس": 3, "thursday": 3,
    "الجمعه": 4, "friday": 4,
    "السبت": 5, "saturday": 5,
    "الاحد": 6, "sunday": 6,
}
_WEEKDAYS = {_n(k): v for k, v in _WEEKDAYS.items()}

_TODAY = ("اليوم", "هاليوم", "الليله", "هالليله", "today", "tonight")
_TOMORROW = ("بكرا", "بكره", "بكرة", "باكر", "غدا", "الغد", "tomorrow")
_AFTER_TOMORROW = ("بعد بكرا", "بعد بكره", "بعد باكر", "بعد غد",
                   "day after tomorrow")


def _date(text: str):
    """يعيد تاريخاً داخل نافذة الحجز فقط، أو None.

    يُفحص «بعد بكرا» قبل «بكرا» لأن الثانية جزء من الأولى.
    """
    days = booking.bookable_days()
    if not days:
        return None
    window = set(days)
    today = config.today_local()

    for word in _AFTER_TOMORROW:
        if _n(word) in text:
            day = today + timedelta(days=2)
            return day if day in window else None
    for word in _TOMORROW:
        if _n(word) in text:
            day = today + timedelta(days=1)
            return day if day in window else None
    for word in _TODAY:
        if _n(word) in text:
            return today if today in window else None

    # اسم اليوم يعني أقرب وقوع له داخل النافذة.
    for name, index in _WEEKDAYS.items():
        if re.search(r"(?:^|\s)" + re.escape(name) + r"(?:\s|$)", text):
            for day in days:
                if day.weekday() == index:
                    return day
    return None


# -------------------------------------------------------- نوع الجلسة
_FAMILY = ("عائلي", "عائله", "عائلات", "عيله", "عايله", "مع العيله",
           "مع الاهل", "family", "families")
_SINGLES = ("شباب", "عزاب", "فردي", "سنجل", "singles", "single",
            "مع الشباب", "شبابي")


def _type(text: str):
    for word in _SINGLES:
        if _n(word) in text:
            return "singles"
    for word in _FAMILY:
        if _n(word) in text:
            return "family"
    return None


# ---------------------------------------------------------------- الواجهة
FIELDS = ("type", "date", "hour", "party", "period")


def extract(text: str) -> dict:
    """يعيد الحقول التي حملتها الرسالة فعلاً — بلا مفاتيح فارغة.

    غياب المفتاح يعني «لم يُذكر»، لا «قيمة فارغة». هذا ما يسمح للمحادثة
    بدمج الجديد فوق القديم دون أن تمحو حقلاً سبق أن قاله الزبون.
    """
    body = normalize(text)
    if not body.strip():
        return {}

    found: dict = {}

    hour, span = _hour(body)
    if hour:
        found["hour"] = hour
    # يُمحى موضع الساعة قبل البحث عن العدد: «الساعة 4» ليست أربعة أشخاص.
    rest = (body[:span[0]] + " " + body[span[1]:]) if span else body

    party = _party(rest)
    if party:
        found["party"] = party

    day = _date(body)
    if day:
        found["date"] = day.isoformat()

    kind = _type(body)
    if kind:
        found["type"] = kind

    # الفترة مفيدة فقط حين لا ساعة صريحة — تختصر شاشة كاملة.
    if "hour" not in found:
        period = _period(body)
        if period:
            found["period"] = period

    return found


def count(found: dict) -> int:
    """عدد الحقول الجوهرية — الفترة وحدها لا تكفي لبدء حجز."""
    return sum(1 for key in ("type", "date", "hour", "party") if key in found)


# ------------------------------------------------------------ رقم الهاتف
# الرقم المنطوق: النسخ الصوتي قد يعيد الخانات كلماتٍ، فرقم صحيح تماماً
# يُرفض وكأنه غير واضح. هذا مسار احتياطي بحت — لا يُجرَّب إلا حين لا
# تكفي الخانات الفعلية — فلا يمسّ الإدخال المكتوب أصلاً.
_SPOKEN_DIGITS = {
    "صفر": "0", "سفر": "0", "zero": "0", "oh": "0",
    "واحد": "1", "one": "1",
    "اثنين": "2", "اتنين": "2", "تنين": "2", "اثنان": "2", "two": "2",
    "ثلاثة": "3", "تلاتة": "3", "three": "3",
    "أربعة": "4", "اربعة": "4", "four": "4",
    "خمسة": "5", "five": "5",
    "ستة": "6", "six": "6",
    "سبعة": "7", "seven": "7",
    "ثمانية": "8", "تمانية": "8", "تمن": "8", "eight": "8",
    "تسعة": "9", "nine": "9",
}
_SPOKEN_DIGITS = {_n(k): v for k, v in _SPOKEN_DIGITS.items()}


def digits_only(text: str) -> str:
    """الخانات وحدها، بعد توحيد الأرقام العربية إلى لاتينية."""
    return "".join(ch for ch in normalize(text) if ch.isdigit())


def phone_digits(text: str) -> str:
    """خانات رقم الهاتف، مكتوبةً كانت أو منطوقة."""
    digits = digits_only(text)
    if len(digits) >= 9:
        return digits
    spoken = "".join(_SPOKEN_DIGITS.get(word, "")
                     for word in re.split(r"[^\w]+", normalize(text)))
    return spoken if len(spoken) >= 9 else digits


# -------------------------------------------------------------- التحية
# التحية الاستهلالية إشارةُ «فاتحة محادثة»: من يبدأ بها لا يكمّل جواباً
# عن سؤال سابق. تُطابَق بحدود كلمات لا بتضمين، وإلا التقطت «هلا» داخل
# «مهلاً» و«hi» داخل «this».
_GREETINGS = (
    "مرحبا", "مرحبتين", "هلا", "اهلا", "اهلين", "يا هلا",
    "السلام عليكم", "سلام عليكم", "صباح الخير", "مساء الخير",
    "hi", "hello", "hey", "heya", "hiya",
    "good morning", "good evening", "good afternoon", "greetings",
)
_GREETING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(_n(g)) for g in _GREETINGS) + r")\b")


def is_greeting(text: str) -> bool:
    """هل تحمل الرسالة تحيةً استهلالية؟"""
    return bool(_GREETING_RE.search(normalize(text)))


def hour_from(text: str):
    """ساعة من رسالة قد تكون رقماً مجرّداً.

    تُستعمل حيث سُئل عن الساعة وحدها: الرقم المجرّد لا يملأ ساعةً في
    الاستخراج العام لأنه بلا مرساة، لكنه هنا جوابٌ عن سؤال صريح —
    والسؤال هو المرساة.
    """
    found = extract(text)
    if found.get("hour"):
        return found["hour"]
    digits = digits_only(text)
    if digits and len(digits) <= 2:
        return _to_evening(int(digits))
    return None
