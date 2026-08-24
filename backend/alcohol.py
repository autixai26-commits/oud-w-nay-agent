# -*- coding: utf-8 -*-
"""فحص قاعدة الكحول (SPEC 7.3) — يُستعمل قبل التحميل وبعده."""
import re

import config

_TOKEN = re.compile(r"[^\w]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.split(text or "") if t]


def scan_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """يعيد (مطابقات مؤكدة، مطابقات تحتاج مراجعة).

    المؤكدة  : كلمة كاملة تطابق مصطلحاً كحولياً — خرق صريح للقاعدة.
    للمراجعة : المصطلح ظهر داخل كلمة أطول — غالباً بريء، يُعرض للتأكيد فقط.
    """
    hard, soft = [], []
    for it in items:
        ar, en = it.get("name_ar", ""), it.get("name_en", "")
        ar_tokens = tokens(ar)
        en_tokens = [t.lower() for t in tokens(en)]

        for term in config.ALCOHOL_TERMS_AR:
            if term in ar_tokens:
                hard.append({"name_ar": ar, "name_en": en, "term": term})
            elif term in ar and len(term) >= 4:
                soft.append({"name_ar": ar, "name_en": en, "term": term})

        for term in config.ALCOHOL_TERMS_EN:
            if term in en_tokens:
                hard.append({"name_ar": ar, "name_en": en, "term": term})
            elif len(term) >= 4 and term in en.lower():
                soft.append({"name_ar": ar, "name_en": en, "term": term})
    return hard, soft
