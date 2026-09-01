# -*- coding: utf-8 -*-
"""فهم تعليمات الأدمن الحرة — SPEC 10.2.

المشكلة التي تحلّها: صلاحية الأدمن كانت تعيش لحظةَ أمر السلاش وحدها.
أما رسالة نصية حرة من الأدمن نفسه فتسلك مسار الزبون، فيردّ البوت على
«الطاولة 33 صارت متاحة» برسالة تسويقية فيها رقم المطعم، وعلى «عدّلها
على موقع الحجز» بـ«ما عندك حجوزات قادمة» — يبحث عن حجوزات شخصية لصاحب
المطعم.

البناء هو بناء detect_intent وslots نفسه: استخراج مُهيكل بمرساة صريحة
يعيد **وجهةَ أمر إداري** لا نصاً. فالأمر الحر وأمر السلاش يلتقيان عند
نفس المنفّذ، ولا يوجد منطق إداري مكرّر في مكانين.

ثلاث طبقات لا طبقتان، وهذا مقصود:
  1. أمر إداري واضح  -> يُنفَّذ.
  2. إشارة إدارية غامضة -> سؤال توضيحي **بصفته أدمن**.
  3. لا إشارة إدارية أصلاً -> مسار الزبون كما هو.

الطبقة الثالثة ليست تساهلاً: صاحب المطعم هو الأدمن نفسه، وهو يجرّب
البوت زبوناً ويتصفّح المنيو ويحجز. لو خُطفت كل رسائله إلى المسار
الإداري لَما استطاع استعمال بوته. الفصل يكون بالمحتوى لا بالهوية.

والأمر يحمل **قائمة طاولات لا طاولةً واحدة**، وتاريخاً صريحاً إن ذُكر.
كلاهما كان مفقوداً: «طاولة 35 و36» كانت تُقرأ 35 وحدها، و«بكرا» كانت
تُهمَل فيُفحص اليومُ دائماً.
"""
import re

import slots

# ------------------------------------------------------------- المفردات
# «طوله» و«طاوله» و«الطاولة» إملاءات واحدة في الكتابة السريعة — وردت
# «طوله» فعلاً في رسالة الأدمن. الرقم مرساةٌ إلزامية: «بدي احجز طاولة»
# بلا رقم ليست أمراً إدارياً.
# [^\W\d] حرفٌ لا رقم: لولاه لابتلع \w* الرقمَ في «طاولة36»
# فقُرئت الطاولةُ 6.
_TABLE = re.compile(
    r"(?:طاول[^\W\d]*|طول[^\W\d]*|table)\s*(?:رقم\s*)?(\d{1,2})")
_BARE_NUMBER = re.compile(r"(?:^|\s)رقم\s*(\d{1,2})(?:\s|$)")
# سلسلة أرقام معطوفة تلي المرساة: «طاولة 35 و36 و37».
_MORE_NUMBERS = re.compile(r"\A\s*(?:و|,|،|&|and)\s*(\d{1,2})")

_FREE = ("متاحه", "متاح", "متاحات", "متاحتين", "فاضيه", "فاضي", "فاضيات",
         "فضيت", "فضت", "فضيوا", "فضيها", "فضيهم", "خلصت", "خلص",
         "خلصوا", "طلعوا", "راحوا", "مشيوا", "حرر", "حررها", "حررهم",
         "فرغ", "فرغت", "فرغها", "قامو", "قاموا",
         "free", "freed", "empty", "available", "left", "done")

_BUSY = ("محجوزه", "محجوز", "محجوزات", "محجوزتين", "مشغوله", "مشغول",
         "معموره", "busy", "occupied", "taken", "reserved")

_LIST = ("حجوزات اليوم", "شو عندنا اليوم", "شو في اليوم", "مين حاجز",
         "مين جاي", "جدول اليوم", "قائمه اليوم", "todays bookings",
         "bookings today", "today bookings")

_STATS = ("الاشغال", "اشغال", "كم حجز", "الاحصائيات", "احصائيات",
          "occupancy", "stats")

# تعديل بلا هدف صريح: «عدّلها على موقع الحجز».
_EDIT = ("عدل", "عدلها", "عدله", "عدلهم", "غير", "غيرها", "حدث", "حدثها",
         "حدثه", "حدثهم", "حول", "حولها", "خليها", "خليهم", "update")

# فعل الحجز الصريح يحسم الاتجاه بلا غموض: «احجزلي طاولة 20» أمرُ حجز
# لا سؤالٌ عن التحرير. ورقم الطاولة نفسه علامةٌ إدارية — الزبون لا
# يختار طاولةً برقمها في المحادثة أصلاً، بل على الخريطة.
_BOOK_VERB = ("احجز", "احجزلي", "احجزها", "احجزهم", "احجزي", "ثبت",
              "ثبتها", "احجزلنا", "book", "reserve", "hold", "block")

# «وطاولة 36 كمان» ترث فعل آخر أمر نُفِّذ في هذه المحادثة.
_CONTINUE = ("كمان", "وكذلك", "كذلك", "زيها", "مثلها", "برضو", "بردو",
             "ايضا", "also", "too", "as well", "same")

_YES = ("اه", "ايه", "اي", "نعم", "تمام", "اكيد", "صح", "yes", "yep",
        "yeah", "ok", "okay", "sure")
_NO = ("لا", "no", "nope", "مش هيك", "غلط")

# «احجز لأحمد» أمرٌ إداري، و«احجزلي» طلبُ زبون. اللام الفارقة تفصل
# بينهما، فنستثني «لي» و«لنا» و«لحالنا» صراحةً. ولا تكفي وحدها: «بدي
# احجز لحالنا» تجتاز اللام لكن «بدي» تعلن أن صاحبها زبون يطلب لنفسه،
# لا أدمن يأمر. فعل الأمر المجرّد هو المرساة، وأي فعل رغبة يُلغيها.
_BOOK_FOR = re.compile(r"احجز\s*ل(?!ي\b|نا\b|حال)\s*\w+")
_WANTS = re.compile(
    r"\b(?:بدي|بدنا|بدها|بدهم|ابغى|اريد|عايز|ودي|wanna|i want|i'd like)\b")

# رمز الحجز ستّ خانات، وقد تفصله كلمة عن الفعل: «الغِ الحجز ABC123».
_CANCEL_CODE = re.compile(
    r"(?:الغ\w*|احذف|شيل|cancel)\b[\s\S]{0,14}?\b([a-z0-9]{6})\b")


# السوابق العربية تلتصق بالكلمة: «لمتاح» و«المتاحة» و«بمتاح» كلها
# «متاح». الحدُّ وحده لا يراها لأن اللام حرفُ كلمة، فنسمح بحرف جرٍّ
# واحد و«ال» قبلها — ولا نتساهل أكثر: «تخلّص» تبقى خارج «خلص» لأن
# التاء ليست من حروف الجر.
_PROCLITIC = r"(?<![^\W\d])[لبوفك]?(?:ال)?"


def _has(body: str, words) -> bool:
    """مطابقة بحدود كلمات لا بتضمين، مع تجاوز السوابق الملتصقة."""
    return any(re.search(_PROCLITIC + re.escape(w) + r"\b", body)
               for w in words)


def _numbers(body: str, loose=False) -> list:
    """كل أرقام الطاولات في الرسالة بترتيب ورودها، بلا تكرار.

    الأمر قد يحمل أكثر من طاولة: «طاولة 35 و36». تُلتقط المرساة أولاً
    ثم تُتبَع سلسلة المعطوفات بعدها مباشرةً، فلا يُخلط رقمُ طاولة برقم
    ساعة: «الطاولة 35 محجوزة الساعة 8» طاولةٌ واحدة، لأن «محجوزة»
    تقطع السلسلة قبل الثمانية.
    """
    found = []
    for match in _TABLE.finditer(body):
        found.append(int(match.group(1)))
        tail = body[match.end():]
        while True:
            more = _MORE_NUMBERS.match(tail)
            if not more:
                break
            found.append(int(more.group(1)))
            tail = tail[more.end():]
    if not found:
        match = _BARE_NUMBER.search(body)
        if match:
            found.append(int(match.group(1)))
    if not found and loose:
        # فعلٌ صريح بلا كلمة «طاولة»: «حرر 35 و36». يُمحى موضع الساعة
        # أولاً فلا تُقرأ ساعةٌ طاولةً، ويُستبعد ما يتبعه اسمُ أشخاص.
        rest = slots.strip_hour(body)
        for match in re.finditer(r"(?<!\d)(\d{1,2})(?!\d)", rest):
            after = rest[match.end():]
            if re.match(r"\s*(?:اشخاص|شخص|نفر|افراد|ناس|people|persons)",
                        after):
                continue
            found.append(int(match.group(1)))
    seen, out = set(), []
    for number in found:
        if number not in seen:
            seen.add(number)
            out.append(number)
    return out


def table_numbers(text: str) -> list:
    """أرقام الطاولات في الرسالة — تُميّز الأمر الجديد عن جواب سؤال."""
    return _numbers(slots.normalize(text))


def table_number(text: str):
    numbers = table_numbers(text)
    return numbers[0] if numbers else None


def understand(text: str, last_table=None, last_action=None):
    """يعيد (وجهة، معطى) أو None حين لا إشارة إدارية إطلاقاً.

    ``last_table`` رقم الطاولة الذي ذكره هذا الأدمن آخر مرة، فيحلّ
    ضمير «عدّلها» — الرسالة التي تلي «الطاولة 33 متاحة» تعني الطاولة
    نفسها، وهو ما يفعله أي إنسان في المحادثة.

    ``last_action`` فعلُ آخر أمر نُفِّذ، ترثه رسالةُ متابعة مثل «وطاولة
    36 كمان»، أو تصحيحُ تاريخ مثل «بكرا مو اليوم»: كلمةُ الاستمرار
    والتاريخُ المصحَّح كلاهما يحيل على الفعل السابق كما يحيل الضمير على
    الاسم السابق.
    """
    body = slots.normalize(text)
    if not body.strip():
        return None

    freed_verb = _has(body, _FREE)
    booked_verb = _has(body, _BOOK_VERB) or _has(body, _BUSY)
    # الرقم المجرّد لا يصير طاولةً إلا خلف فعل إداري صريح، ولا يصير
    # حتى حينها إن أعلن قائلُه أنه زبون يطلب لنفسه.
    loose = (freed_verb or booked_verb) and not _WANTS.search(body)
    numbers = _numbers(body, loose=loose)
    found = slots.extract(text)
    day = found.get("date")

    # -------------------------------------------------- أوامر واضحة
    match = _CANCEL_CODE.search(body)
    if match:
        return ("cancel", match.group(1).upper())

    if _BOOK_FOR.search(body) and not _WANTS.search(body):
        return ("book", None)

    if any(w in body for w in _LIST):
        return ("today", None)

    if _has(body, _STATS):
        return ("stats", None)

    freed, booked = freed_verb, booked_verb

    if numbers:
        # SPEC 10.2.1 — حجز إداري: الوقت وحده مطلوب، ويُقرأ من الجملة
        # نفسها إن ذُكر فيها. لا اسم ولا هاتف، فليس حجز زبون.
        if booked:
            return ("block", (numbers, found.get("hour"), day))
        if freed:
            return ("free", (numbers, day))

        # لا فعل: ترث الرسالةُ فعلَ آخر أمر نُفِّذ إن أعلنت الاستمرار.
        if _has(body, _CONTINUE) and last_action in ("free", "block"):
            if last_action == "free":
                return ("free", (numbers, day))
            return ("block", (numbers, found.get("hour"), day))

        # رقم طاولة بلا فعل ولا استمرار: غامضة لا رسالة زبون.
        return ("clarify_free", (numbers, day))

    # ------------------------------- بلا رقم: الكلام يحيل على ما سبق
    if last_table is not None:
        if freed:
            return ("free", ([last_table], day))
        if booked:
            return ("block", ([last_table], found.get("hour"), day))
        # «بكرا مو اليوم» تصحيحُ تاريخٍ لأمرٍ نُفِّذ للتوّ، لا حديثٌ جديد.
        if day and last_action in ("free", "block"):
            if last_action == "free":
                return ("free", ([last_table], day))
            return ("block", ([last_table], found.get("hour"), day))
        if _has(body, _EDIT):
            return ("clarify_free", ([last_table], day))

    if _has(body, _EDIT):
        return ("clarify_target", None)

    # لا إشارة إدارية: رسالة زبون عادية من صاحب المطعم.
    return None


def answer_to_clarify(text: str):
    """يقرأ جواب الأدمن على سؤال توضيحي: 'free' أو 'block' أو 'yes'/'no'.

    الفعل الصريح يسبق الإيجاب والنفي: «لا احجزها» نفيٌ للاقتراح وأمرٌ
    بالعكس معاً، ومعناها الحقيقي في الفعل لا في «لا». من قرأ «لا» وحدها
    خسر التصحيح كلّه.
    """
    body = slots.normalize(text)
    if not body.strip():
        return None
    if _has(body, _BOOK_VERB) or _has(body, _BUSY):
        return "block"
    if _has(body, _FREE):
        return "free"
    if _has(body, _YES):
        return "yes"
    if _has(body, _NO):
        return "no"
    return None


def has_admin_fragment(text: str) -> bool:
    """هل في الرسالة شظيّةٌ إدارية وإن لم تكتمل أمراً؟

    حارسٌ أخير: أدمنٌ في سياق إداري قائم لا يجوز أن ينزل ردُّه إلى
    ترحيب الزبون لمجرّد أن جملته لم تكتمل أمراً. «بكرا مو اليوم»
    شظيّةُ تاريخ، و«اه» شظيّةُ إيجاب — كلتاهما تخصّ ما قبلها، لا
    محادثةً جديدة. أما سؤالٌ حقيقي بلا أي شظيّة فيمضي لمسار الزبون
    كما كان، فصاحب المطعم يسأل بوته أحياناً.
    """
    body = slots.normalize(text)
    if not body.strip():
        return False
    return bool(
        _numbers(body, loose=True) or slots.extract(text).get("date")
        or _has(body, _FREE) or _has(body, _BUSY) or _has(body, _BOOK_VERB)
        or _has(body, _EDIT) or _has(body, _YES) or _has(body, _NO)
        or _has(body, _CONTINUE))
