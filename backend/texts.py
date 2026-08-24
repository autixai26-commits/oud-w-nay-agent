# -*- coding: utf-8 -*-
"""كل نصوص البوت بالعربية والإنجليزية.

SPEC 8: ممنوع كتابة أي نص موجّه للزبون داخل منطق الكود — كله هنا.
الشخصية: فرح، مضيفة عود وناي. نبرة رسمية ودودة، مؤنثة، لهجة أردنية
طبيعية غير مبالغ فيها، وإيموجي واحد أو اثنان كحد أقصى في الرسالة.
"""
import config

MAPS_URL = "https://maps.app.goo.gl/VKfayTxhN2CSnE1VA?g_st=ic"
INSTAGRAM_URL = "https://www.instagram.com/oudandnay"

AR = {
    # ---------------------------------------------------------- اللغة
    "choose_language": "أهلاً وسهلاً في عود وناي 🌿\nاختر لغتك المفضّلة:",
    "btn_lang_ar": "🇯🇴 عربي",
    "btn_lang_en": "🇬🇧 English",
    "language_set": "تمام، رح نكمل بالعربي.",
    "btn_switch_lang": "🇬🇧 English",

    # ------------------------------------------------- القائمة الرئيسية
    "welcome": ("أهلاً فيك في مطعم عود وناي 🌿\n"
                "أنا فرح، بخدمتك. شو بتحب تشوف؟"),
    "main_menu": "شو بتحب تشوف؟",
    "btn_menu": "🍽️ المنيو",
    "btn_book": "🪑 احجز طاولة",
    "btn_info": "ℹ️ معلومات المطعم",
    "btn_back": "◀️ رجوع",
    "btn_main_menu": "🏠 القائمة الرئيسية",
    "btn_prev": "◀️ السابق",
    "btn_next": "التالي ▶",

    # ------------------------------------------------ معلومات المطعم
    "info_menu": "أي معلومة بتحب تعرفها؟",
    "btn_location": "📍 الموقع",
    "btn_hours": "🕐 الدوام",
    "btn_phone": "☎️ الهاتف",
    "btn_happy_hour": "🎉 هابي أور",
    "btn_shisha": "💨 الأرجيلة",

    "location": ("مطعم عود وناي — الفحيص، دوار الحصان 📍\n\n"
                 "على خرائط جوجل:\n{maps}\n\n"
                 "وإنستغرامنا: {instagram}"),
    "hours": ("دوامنا كل يوم من الساعة 1:00 الظهر حتى 12:00 منتصف الليل 🕐\n"
              "ما عندنا عطلة أسبوعية — مفتوحين طول الأسبوع."),
    "phone": ("تقدر تتصل فينا على {phone} ☎️\n"
              "بنستقبل استفساراتك وحجوزاتك بكل ترحيب."),
    "happy_hour": ("هابي أور: خصم 25% على كامل الفاتورة 🎉\n\n"
                   "من السبت إلى الخميس، من الساعة 1:00 حتى 6:00 مساءً.\n"
                   "الجمعة مستثناة من العرض.\n\n"
                   "الأسعار لا تشمل 5% خدمة و7% ضريبة."),
    "shisha_info": ("عندنا أرجيلة بنكهات متعددة 💨\n\n"
                    "أرجيلة عود وناي · جميع النكهات · نفاحتين نخلة · عجمي\n\n"
                    "تقدر تشوف الأسعار من المنيو ← أرجيلة."),

    # -------------------------------------------------------- المنيو
    "menu_root": "المنيو عندنا 🍽️\nمن وين تحب تبلّش؟",
    "btn_food": "🍽️ أكل",
    "btn_drinks": "🥤 مشروبات",
    "btn_shisha_menu": "💨 أرجيلة",
    "pick_category": "اختر القسم:",
    "pick_subcategory": "اختر الصفحة:",
    "page_of": "صفحة {page} من {pages}",
    "tax_note": "الأسعار لا تشمل 5% خدمة و7% ضريبة.",
    "price_unit": "د.أ",

    # ------------------------------------------------- ردود خاصة
    # SPEC 7.3: هذه الصيغة حرفياً، بدون تأكيد ولا نفي، ولا يفتح البوت الموضوع.
    "alcohol": ("المنيو المتوفر عندي هو الأكل والمشروبات الساخنة "
                "والباردة والأرجيلة 🌿 — تفضّل شو بتحب تشوف؟"),
    # SPEC 8: ممنوع الاختراع.
    "unknown": ("هاي المعلومة مش متوفرة عندي — بتقدر تتواصل معنا "
                "على {phone} وبيفيدوك 🙏"),
    "off_topic": ("أنا بخدمتك بكل إشي يخص مطعم عود وناي 🌿 "
                  "بتحب تشوف المنيو أو تعرف عن الحجز؟"),
    "no_delivery": ("للأسف ما عندنا توصيل ولا طلبات خارجية — "
                    "بنستناك عندنا بالمطعم، أو اتصل فينا على {phone} 🙏"),
    "booking_soon": ("الحجز من البوت لسا قيد التجهيز 🪑\n"
                     "لحد ما يجهز، تقدر تحجز باتصال على {phone} "
                     "وبنحجزلك على طول."),
    "error": "صار عندنا خلل بسيط، جرّب كمان مرة بعد شوي 🙏",
    "typing": "لحظة…",
}

EN = {
    "choose_language": "Welcome to Oud w Nay 🌿\nPlease choose your language:",
    "btn_lang_ar": "🇯🇴 عربي",
    "btn_lang_en": "🇬🇧 English",
    "language_set": "Great, we'll continue in English.",
    "btn_switch_lang": "🇯🇴 عربي",

    "welcome": ("Welcome to Oud w Nay Lebanese Restaurant 🌿\n"
                "I'm Farah, at your service. What would you like to see?"),
    "main_menu": "What would you like to see?",
    "btn_menu": "🍽️ Menu",
    "btn_book": "🪑 Book a table",
    "btn_info": "ℹ️ Restaurant info",
    "btn_back": "◀️ Back",
    "btn_main_menu": "🏠 Main menu",
    "btn_prev": "◀️ Previous",
    "btn_next": "Next ▶",

    "info_menu": "What would you like to know?",
    "btn_location": "📍 Location",
    "btn_hours": "🕐 Opening hours",
    "btn_phone": "☎️ Phone",
    "btn_happy_hour": "🎉 Happy hour",
    "btn_shisha": "💨 Shisha",

    "location": ("Oud w Nay Restaurant — Fuheis, Al-Hosan Roundabout 📍\n\n"
                 "On Google Maps:\n{maps}\n\n"
                 "Our Instagram: {instagram}"),
    "hours": ("We're open every day from 1:00 PM until 12:00 midnight 🕐\n"
              "No weekly closing day — open all week."),
    "phone": ("You can reach us at {phone} ☎️\n"
              "We're happy to take your questions and bookings."),
    "happy_hour": ("Happy hour: 25% off your entire bill 🎉\n\n"
                   "Saturday through Thursday, from 1:00 PM to 6:00 PM.\n"
                   "Friday is excluded from the offer.\n\n"
                   "Prices exclude 5% service and 7% tax."),
    "shisha_info": ("We serve shisha in a range of flavours 💨\n\n"
                    "Oud w Nay · All flavours · Two-Apple Nakhla · Ajami\n\n"
                    "You can see prices under Menu → Shisha."),

    "menu_root": "Here's our menu 🍽️\nWhere would you like to start?",
    "btn_food": "🍽️ Food",
    "btn_drinks": "🥤 Drinks",
    "btn_shisha_menu": "💨 Shisha",
    "pick_category": "Choose a section:",
    "pick_subcategory": "Choose a page:",
    "page_of": "Page {page} of {pages}",
    "tax_note": "Prices exclude 5% service charge and 7% sales tax.",
    "price_unit": "JOD",

    "alcohol": ("Our menu covers food, hot and cold drinks, and shisha 🌿 "
                "— what would you like to see?"),
    "unknown": ("I don't have that information — you can reach us "
                "at {phone} and they'll help you 🙏"),
    "off_topic": ("I'm here for anything about Oud w Nay Restaurant 🌿 "
                  "Would you like to see the menu or ask about booking?"),
    "no_delivery": ("We don't offer delivery or takeaway — we'd love to "
                    "host you at the restaurant, or call us at {phone} 🙏"),
    "booking_soon": ("Booking through the bot is still being set up 🪑\n"
                     "In the meantime, call us at {phone} and we'll "
                     "reserve your table right away."),
    "error": "Something went wrong on our side, please try again shortly 🙏",
    "typing": "One moment…",
}

_TABLES = {"ar": AR, "en": EN}
DEFAULT_LANG = "ar"


def t(lang: str, key: str, **kwargs) -> str:
    """يعيد النص بالمفتاح واللغة المطلوبة، مع تعبئة المتغيرات الشائعة."""
    table = _TABLES.get(lang or DEFAULT_LANG, AR)
    text = table.get(key) or AR.get(key, "")
    return text.format(phone=config.RESTAURANT_PHONE, maps=MAPS_URL,
                       instagram=INSTAGRAM_URL, **kwargs)


def price(value, lang: str) -> str:
    """السعر بالدينار بثلاث خانات عشرية — SPEC 7.4."""
    return "%.3f %s" % (float(value), t(lang, "price_unit"))
