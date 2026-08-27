# -*- coding: utf-8 -*-
"""التذكيرات والإلغاء التلقائي — SPEC 6.3.5 و 6.4.

التصميم: مسح دوري لقاعدة البيانات، لا جدولة مهمة لكل حجز في الذاكرة.
السبب أن Render يعيد تشغيل الخدمة عند كل نشر وعند أي خلل، وأي مهمة
مجدولة في الذاكرة تضيع عندها بلا أثر — بينما المسح يلتقط ما فات.

كل المدد تمر بـ config.minutes() (القيد ٢)، فيكفي ضبط TEST_TIME_SCALE
لتشغيل السيناريو كاملاً بالثواني بدل الدقائق.

كل إجراء يُحجز في القاعدة قبل تنفيذه لا بعده. المقايضة مقصودة: لو فشل
الإرسال بعد الحجز ضاعت الرسالة، ولو حُجز بعد الإرسال وصلت مرتين. تكرار
تذكير على الزبون أسوأ من سقوطه، وسقوطه يظهر في اللوق.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

import admin
import config
import db
import texts
from platform_adapter import User, get as get_adapter

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _ts(value: str):
    from datetime import datetime
    return datetime.fromisoformat(value)


def _due(moment: str, offset) -> bool:
    """هل حان وقت الإجراء؟ offset موجب = بعد الموعد، سالب = قبله."""
    return _ts(moment) + offset <= config.now_utc()


def tick() -> dict:
    """دورة مسح واحدة. تعيد عدّاد ما نُفِّذ — يستعمله سكربت التحقق."""
    done = {"alert2": 0, "reminder": 0, "attendance": 0, "auto_cancel": 0}
    now = config.now_utc()

    from platform_adapter import ADAPTERS

    for res in db.reservations_by_status(["pending", "confirmed"]):
        # منصّة لا محوّل لها لا يمكن إشعار صاحبها أصلاً، فتخطّيها هو
        # السلوك الصحيح. وله أثر عملي مهم: بيئة الاختبار تستعمل منصّة
        # خاصة بها، فلا تلتقط خدمةُ الإنتاج صفوفَ الاختبار ولا تستهلك
        # تذكيراتها — وكلتاهما تمسحان قاعدة البيانات نفسها.
        if res.get("platform") not in ADAPTERS:
            continue
        try:
            # -------- تنبيه الأدمن الثاني بعد 15 دقيقة بلا رد (SPEC 6.3.5)
            if (res["status"] == "pending"
                    and not res.get("admin_alert2_at")
                    and not res.get("is_large_group")
                    and _due(res["created_at"],
                             config.minutes(config.ADMIN_SECOND_ALERT_MIN))):
                # يُحجز أولاً ثم يُرسَل: من خسر الحجز لا يرسل شيئاً.
                if not db.claim_reservation(res["id"], "admin_alert2_at",
                                            now.isoformat()):
                    continue
                admin.alert_no_reply(res)
                lang = res.get("language") or "ar"
                get_adapter(res["platform"]).send_text(
                    User(res["platform"], res["user_id"], res["user_id"]),
                    texts.t(lang, "customer_no_answer_yet"))
                done["alert2"] += 1
                continue

            if res["status"] != "confirmed":
                continue

            # -------- الإلغاء التلقائي بعد الموعد بـ30 دقيقة (SPEC 6.4)
            if _due(res["reservation_at"],
                    config.minutes(config.AUTO_CANCEL_AFTER_MIN)):
                if not db.claim_status(res["id"], "confirmed", "no_show"):
                    continue
                fresh = db.get_reservation(res["id"]) or res
                lang = res.get("language") or "ar"
                get_adapter(res["platform"]).send_text(
                    User(res["platform"], res["user_id"], res["user_id"]),
                    texts.t(lang, "auto_cancelled_customer"))
                admin.notify_auto_cancel(fresh)
                done["auto_cancel"] += 1
                continue

            # -------- سؤال الحضور بعد الموعد بـ10 دقائق (SPEC 6.4)
            if (not res.get("attendance_asked_at")
                    and _due(res["reservation_at"],
                             config.minutes(config.ATTENDANCE_ASK_AFTER_MIN))):
                if not db.claim_reservation(res["id"], "attendance_asked_at",
                                            now.isoformat()):
                    continue
                admin.ask_attendance(res)
                done["attendance"] += 1
                continue

            # -------- تذكير الزبون قبل الموعد بـ30 دقيقة (SPEC 6.4)
            # نافذة التذكير [الموعد − 30 دقيقة، الموعد). بعد مرور الموعد
            # يصير التذكير بلا معنى — "موعدك بعد شوي" وهو قد فات — فنسقطه.
            if (not res.get("reminder_sent_at")
                    and _ts(res["reservation_at"]) > config.now_utc()
                    and _due(res["reservation_at"],
                             -config.minutes(config.REMINDER_BEFORE_MIN))):
                if not db.claim_reservation(res["id"], "reminder_sent_at",
                                            now.isoformat()):
                    continue
                lang = res.get("language") or "ar"
                get_adapter(res["platform"]).send_text(
                    User(res["platform"], res["user_id"], res["user_id"]),
                    texts.t(lang, "reminder",
                            table=admin._table_number(res),
                            hall=admin._hall_name(res, lang),
                            time=admin._fmt_time(res)))
                done["reminder"] += 1

        except Exception as exc:  # noqa: BLE001
            # حجز واحد معطوب لا يوقف الدورة كلها.
            log.error("فشل في معالجة الحجز %s: %s",
                      res.get("code"), type(exc).__name__)

    if any(done.values()):
        log.info("دورة الجدولة: %s", done)
    return done


def interval_seconds() -> float:
    """فترة المسح: دقيقة حقيقية، تنكمش مع معامل الاختبار.

    مع TEST_TIME_SCALE=60 تصير ثانية واحدة، فيتحقق سيناريو الـ30 دقيقة
    في 30 ثانية.
    """
    return max(1.0, config.minutes(1).total_seconds())


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(tick, "interval", seconds=interval_seconds(),
                       id="tick", max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("بدأت الجدولة كل %.1f ثانية", interval_seconds())
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
