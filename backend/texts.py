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
    'voice_failed': 'ما قدرت أفهم الرسالة الصوتية منيح 🙏 جرّب تبعتها كمان مرة، أو اكتبلي.',
    'ask_booking_type': 'قبل ما نبلّش — الحجز لعائلة ولا لشباب؟',
    'btn_family': '👨\u200d👩\u200d👧 عائلة',
    'btn_singles': '👥 شباب',
    'ask_date': 'أي يوم بتحب تحجز؟',
    'btn_today': 'اليوم',
    'btn_tomorrow': 'بكرا',
    'ask_period': 'أي وقت بناسبك؟',
    'btn_noon': '🌤️ ظهراً 1–4',
    'btn_evening': '🌆 مساءً 5–8',
    'btn_late': '🌙 سهرة 9–12',
    'ask_hour': 'اختر الساعة:',
    'ask_party': 'كم شخص رح تكونوا؟',
    'btn_party_11': '11 فأكثر',
    'ask_name': 'تكرّماً، شو اسمك؟',
    'ask_phone': 'ممكن رقم تلفونك؟ 🙏',
    'invalid_phone': 'الرقم مش واضح — اكتبه أرقام بس، مثال 0791234567 🙏',
    'happy_hour_notice': 'بالمناسبة، حجزك ضمن وقت الهابي أور — خصم 25% على كامل الفاتورة 🎉',
    'singles_family_day': 'للأسف الخميس والجمعة والسبت المطعم بالكامل للعائلات فقط 🙏\nبتحب تختار يوم تاني؟ من الأحد للأربعاء بنستقبلكم بالصالة الخارجية.',
    'link_ready': 'تمام! ضل بس تختار طاولتك 🪑\n\n{summary}\n\nالرابط صالح 30 دقيقة.',
    'btn_choose_table': '🪑 اختر طاولتك',
    'summary_line': '{date} · {time} · {people} أشخاص · {kind}',
    'kind_family': 'عائلة',
    'kind_singles': 'شباب',
    'booking_pending': 'استنى شوي لحتى نثبّت حجزك ⏳',
    'btn_cancel_booking': '❌ إلغاء',
    'booking_cancelled': 'تمام، لغينا العملية. بتقدر تبلّش من جديد وقت ما بدك.',
    'large_group_intro': 'لأنكم 11 شخص أو أكثر، رح نرتّبلكم الحجز يدوياً 🙏\nبحتاج منك كم معلومة بسيطة.',
    'ask_group_type': 'شو نوع المجموعة؟',
    'btn_group_family': 'عائلة',
    'btn_group_wedding': 'عرس',
    'btn_group_singles': 'شباب',
    'ask_occasion': 'شو المناسبة؟ اكتبها، أو اكتب «لا يوجد».',
    'ask_party_exact': 'كم شخص بالضبط؟ اكتب الرقم.',
    'invalid_number': 'اكتب رقم صحيح من فضلك.',
    'large_group_sent': 'وصلنا طلبك 🙏\n\n{summary}\n\nرح نتواصل معك قريباً لتأكيد التفاصيل. رمز الطلب: {code}',
    'weekdays': 'الاثنين,الثلاثاء,الأربعاء,الخميس,الجمعة,السبت,الأحد',
    'admin_registered': 'تم تسجيلك كأدمن ✅\nرح توصلك إشعارات الحجوزات من هلأ.',
    'admin_bad_secret': 'كلمة السر غير صحيحة.',
    'admin_already': 'إنت مسجّل كأدمن أصلاً ✅',
    'admin_only': 'هذا الأمر للأدمن فقط.',
    'admin_usage': 'الاستخدام: {usage}',
    'admin_new_booking': 'حجز جديد 🔔\n\nالطاولة: {table} · {hall}\nالتاريخ: {date}\nالوقت: {time}\nالعدد: {people}\nالنوع: {kind}\nالاسم: {name}\nالهاتف: {phone}\nالرمز: {code}',
    'admin_large_group': 'طلب مجموعة كبيرة 🔔\n\nالعدد: {people}\nنوع المجموعة: {group}\nالمناسبة: {occasion}\nالتاريخ: {date}\nالوقت: {time}\nالاسم: {name}\nالهاتف: {phone}\nالرمز: {code}\n\nتواصل مع الزبون لترتيب التفاصيل.',
    'btn_admin_confirm': '✅ ثبّت الحجز',
    'btn_admin_reject': '❌ ارفض',
    'admin_decided': 'تم — {who} ردّ: {what}',
    'decision_confirmed': 'ثبّت الحجز',
    'decision_rejected': 'رفض الحجز',
    'admin_alert2': 'تنبيه ⏰ مرّت 15 دقيقة بلا رد على هذا الحجز:\n\n{summary}',
    'customer_confirmed': 'تثبّت حجزك ✅\n\nالطاولة: {table} · {hall}\nالتاريخ: {date}\nالوقت: {time}\nالعدد: {people}\nالاسم: {name}\n\nرمز الحجز: {code}\nبنستناكم 🌿',
    'customer_rejected': 'للأسف الطاولة اللي اخترتها محجوزة، فضلاً اختر طاولة ثانية 🙏',
    'customer_no_answer_yet': 'لسا ما وصلنا تأكيد. إذا ما وصلك رد خلال 10 دقائق، رجاءً اتصل على {phone} 🙏',
    'reminder': 'تذكير بموعدك بعد شوي ⏰\n\nالطاولة: {table} · {hall}\nالوقت: {time}\n\nبنستناك 🌿',
    'admin_attendance_ask': 'إجا زبون طاولة {table}؟\n{name} · {phone}',
    'btn_came': '✅ إجا',
    'btn_no_show': '❌ ما إجا',
    'btn_table_free': '🔓 الطاولة فضيت',
    'admin_marked_seated': 'تم — الزبون على الطاولة {table} ✅',
    'admin_marked_noshow': 'تم — تحرّرت الطاولة {table} ✅',
    'admin_table_freed': 'تحرّرت الطاولة {table} وصارت متاحة اليوم ✅',
    'auto_cancelled_customer': 'أُلغي حجزك تلقائياً لأنه ما وصلنا تأكيد حضورك 🙏\nبتقدر تحجز من جديد وقت ما بدك.',
    'auto_cancelled_admin': 'إلغاء تلقائي ⏰ مرّت 30 دقيقة على الموعد بلا رد:\n\n{summary}\nتحرّرت الطاولة.',
    'btn_my_bookings': '📋 حجوزاتي',
    'my_bookings_title': 'حجوزاتك القادمة:',
    'my_bookings_empty': 'ما عندك حجوزات قادمة حالياً.',
    'res_line': '{code} · {date} · {time} · طاولة {table} · {status}',
    'btn_cancel_res': '❌ إلغاء {code}',
    'btn_edit_res': '✏️ تعديل {code}',
    'res_cancelled': 'تم إلغاء حجزك {code} ✅\nبتقدر تحجز من جديد وقت ما بدك.',
    'admin_customer_cancelled': 'الزبون ألغى حجزه 🔔\n\n{summary}',
    'edit_intro': 'تمام، رح نلغي الحجز القديم ونبلّش حجز جديد.',
    'st_pending': 'بانتظار التثبيت',
    'st_confirmed': 'مثبّت',
    'st_seated': 'على الطاولة',
    'st_rejected': 'مرفوض',
    'st_no_show': 'ما حضر',
    'st_cancelled': 'ملغى',
    'st_completed': 'منتهي',
    'admin_today_title': 'حجوزات {date}:',
    'admin_none': 'ما في حجوزات.',
    'admin_res_line': '{time} · طاولة {table} · {people} أشخاص · {name} · {phone} · {status} · {code}',
    'admin_stats': 'إحصائيات {date} 📊\n\nالحجوزات: {count}\nالطاولات المشغولة: {busy} من {total}\nنسبة الإشغال: {rate}%\nالمقاعد المحجوزة: {seats}',
    'admin_not_found': 'ما لقيت حجز بالرمز {code}.',
    'admin_cancelled_ok': 'تم إلغاء الحجز {code} ✅',
    'admin_table_not_found': 'ما في طاولة برقم {table}.',
    'admin_table_already_free': 'الطاولة {table} متاحة أصلاً اليوم.',
    'admin_help': 'أوامر الأدمن:\n/today — حجوزات اليوم\n/date 2026-09-01 — حجوزات تاريخ\n/cancel رمز — إلغاء حجز\n/edit رمز — تعديل حجز\n/book — حجز يدوي\n/free رقم — تحرير طاولة\n/stats — إحصائيات اليوم',
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
    'voice_failed': "I couldn't quite catch that voice note 🙏 Please try again, or type it.",
    'ask_booking_type': 'First — is this booking for a family or a group of men?',
    'btn_family': '👨\u200d👩\u200d👧 Family',
    'btn_singles': '👥 Men only',
    'ask_date': 'Which day would you like?',
    'btn_today': 'Today',
    'btn_tomorrow': 'Tomorrow',
    'ask_period': 'Which time suits you?',
    'btn_noon': '🌤️ Afternoon 1–4',
    'btn_evening': '🌆 Evening 5–8',
    'btn_late': '🌙 Late 9–12',
    'ask_hour': 'Choose a time:',
    'ask_party': 'How many people?',
    'btn_party_11': '11 or more',
    'ask_name': 'May I have your name?',
    'ask_phone': 'And may I have your phone number? 🙏',
    'invalid_phone': "That number isn't clear — digits only please, e.g. 0791234567 🙏",
    'happy_hour_notice': 'By the way, your booking falls in happy hour — 25% off the entire bill 🎉',
    'singles_family_day': 'Thursday, Friday and Saturday the whole restaurant is families only 🙏\nWould you like another day? Sunday to Wednesday we welcome you in the outdoor hall.',
    'link_ready': 'All set! Just pick your table 🪑\n\n{summary}\n\nThe link is valid for 30 minutes.',
    'btn_choose_table': '🪑 Choose your table',
    'summary_line': '{date} · {time} · {people} people · {kind}',
    'kind_family': 'Family',
    'kind_singles': 'Men only',
    'booking_pending': 'One moment while we confirm your booking ⏳',
    'btn_cancel_booking': '❌ Cancel',
    'booking_cancelled': "No problem, we've cancelled that. Start again anytime.",
    'large_group_intro': "Since you're 11 or more, we'll arrange this booking personally 🙏\nI just need a few details.",
    'ask_group_type': 'What kind of group is it?',
    'btn_group_family': 'Family',
    'btn_group_wedding': 'Wedding',
    'btn_group_singles': 'Men only',
    'ask_occasion': "What's the occasion? Type it, or type 'none'.",
    'ask_party_exact': 'Exactly how many people? Type the number.',
    'invalid_number': 'Please type a valid number.',
    'large_group_sent': "We've received your request 🙏\n\n{summary}\n\nWe'll contact you shortly to confirm. Request code: {code}",
    'weekdays': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday',
    'admin_registered': "You're registered as an admin ✅\nYou'll receive booking notifications from now on.",
    'admin_bad_secret': 'Incorrect password.',
    'admin_already': "You're already registered as an admin ✅",
    'admin_only': 'This command is for admins only.',
    'admin_usage': 'Usage: {usage}',
    'admin_new_booking': 'New booking 🔔\n\nTable: {table} · {hall}\nDate: {date}\nTime: {time}\nPeople: {people}\nType: {kind}\nName: {name}\nPhone: {phone}\nCode: {code}',
    'admin_large_group': 'Large group request 🔔\n\nPeople: {people}\nGroup type: {group}\nOccasion: {occasion}\nDate: {date}\nTime: {time}\nName: {name}\nPhone: {phone}\nCode: {code}\n\nPlease contact the guest to arrange details.',
    'btn_admin_confirm': '✅ Confirm',
    'btn_admin_reject': '❌ Reject',
    'admin_decided': 'Done — {who} replied: {what}',
    'decision_confirmed': 'confirmed',
    'decision_rejected': 'rejected',
    'admin_alert2': 'Reminder ⏰ 15 minutes with no reply on this booking:\n\n{summary}',
    'customer_confirmed': 'Your booking is confirmed ✅\n\nTable: {table} · {hall}\nDate: {date}\nTime: {time}\nPeople: {people}\nName: {name}\n\nBooking code: {code}\nWe look forward to hosting you 🌿',
    'customer_rejected': 'Sorry, the table you picked is taken. Please choose another one 🙏',
    'customer_no_answer_yet': "We haven't received confirmation yet. If you don't hear back within 10 minutes, please call {phone} 🙏",
    'reminder': 'A reminder of your booking shortly ⏰\n\nTable: {table} · {hall}\nTime: {time}\n\nSee you soon 🌿',
    'admin_attendance_ask': 'Did the guest for table {table} arrive?\n{name} · {phone}',
    'btn_came': '✅ Arrived',
    'btn_no_show': '❌ No show',
    'btn_table_free': '🔓 Table is free',
    'admin_marked_seated': 'Done — guest seated at table {table} ✅',
    'admin_marked_noshow': 'Done — table {table} released ✅',
    'admin_table_freed': 'Table {table} is free and available today ✅',
    'auto_cancelled_customer': "Your booking was cancelled automatically as we didn't hear from you 🙏\nYou're welcome to book again anytime.",
    'auto_cancelled_admin': 'Auto-cancelled ⏰ 30 minutes past the time with no reply:\n\n{summary}\nThe table has been released.',
    'btn_my_bookings': '📋 My bookings',
    'my_bookings_title': 'Your upcoming bookings:',
    'my_bookings_empty': 'You have no upcoming bookings.',
    'res_line': '{code} · {date} · {time} · table {table} · {status}',
    'btn_cancel_res': '❌ Cancel {code}',
    'btn_edit_res': '✏️ Edit {code}',
    'res_cancelled': 'Your booking {code} has been cancelled ✅\nYou can book again anytime.',
    'admin_customer_cancelled': 'A guest cancelled their booking 🔔\n\n{summary}',
    'edit_intro': "Sure — we'll cancel the old booking and start a new one.",
    'st_pending': 'awaiting confirmation',
    'st_confirmed': 'confirmed',
    'st_seated': 'seated',
    'st_rejected': 'rejected',
    'st_no_show': 'no show',
    'st_cancelled': 'cancelled',
    'st_completed': 'completed',
    'admin_today_title': 'Bookings for {date}:',
    'admin_none': 'No bookings.',
    'admin_res_line': '{time} · table {table} · {people} people · {name} · {phone} · {status} · {code}',
    'admin_stats': 'Statistics for {date} 📊\n\nBookings: {count}\nTables occupied: {busy} of {total}\nOccupancy: {rate}%\nSeats booked: {seats}',
    'admin_not_found': 'No booking found with code {code}.',
    'admin_cancelled_ok': 'Booking {code} cancelled ✅',
    'admin_table_not_found': "There's no table numbered {table}.",
    'admin_table_already_free': 'Table {table} is already free today.',
    'admin_help': "Admin commands:\n/today — today's bookings\n/date 2026-09-01 — bookings for a date\n/cancel CODE — cancel a booking\n/edit CODE — edit a booking\n/book — manual booking\n/free NUMBER — release a table\n/stats — today's statistics",
}

_TABLES = {"ar": AR, "en": EN}
DEFAULT_LANG = "ar"


def t(lang: str, key: str, **kwargs) -> str:
    """يعيد النص بالمفتاح واللغة المطلوبة، مع تعبئة المتغيرات الشائعة."""
    table = _TABLES.get(lang or DEFAULT_LANG, AR)
    text = table.get(key) or AR.get(key, "")
    # القيم الشائعة تُعبّأ تلقائياً، لكن الوسيط الصريح يطغى عليها:
    # إشعار الأدمن يمرّر هاتف الزبون في {phone} لا هاتف المطعم.
    values = {"phone": config.RESTAURANT_PHONE, "maps": MAPS_URL,
              "instagram": INSTAGRAM_URL}
    values.update(kwargs)
    return text.format(**values)


def price(value, lang: str) -> str:
    """السعر بالدينار بثلاث خانات عشرية — SPEC 7.4."""
    return "%.3f %s" % (float(value), t(lang, "price_unit"))


# ------------------------------------------------- كشف اللغة (SPEC 8)
# شاشة اختيار اللغة الإجبارية أُلغيت: نكتشفها من أول رسالة ونبدأ فوراً.
import re as _re

_ARABIC = _re.compile(r"[\u0600-\u06FF]")
_LATIN = _re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """يعيد 'ar' أو 'en' حسب الحروف الغالبة في الرسالة.

    نعتمد الحروف لا النموذج: الكشف يجب أن يكون فورياً ومجانياً ولا
    يفشل عند انقطاع الشبكة. عند التعادل أو الغموض نرجّح العربية،
    فهي لغة أغلب زبائن المطعم.
    """
    body = text or ""
    ar = len(_ARABIC.findall(body))
    en = len(_LATIN.findall(body))
    if en > ar * 2 and en >= 3:
        return "en"
    return DEFAULT_LANG
