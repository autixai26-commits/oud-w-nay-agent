# -*- coding: utf-8 -*-
"""نقطة التشغيل: FastAPI + webhook تليجرام + REST API.

المرحلة 2 تغطّي الـwebhook والمحادثة. الـREST API الخاص بالحجز
يُضاف في المرحلة 3.
"""
import hashlib
import hmac
import logging

from fastapi import FastAPI, Header, Request, Response

import config
import conversation
import db
import telegram_api
from platform_adapter import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# القيد ٤: httpx يسجّل رابط كل طلب على مستوى INFO، وفيه رابط مشروع
# Supabase كاملاً — وهو يظهر عندها في لوغات Render. نرفعه إلى WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

log = logging.getLogger("oud-w-nay")

app = FastAPI(title="Oud w Nay", docs_url=None, redoc_url=None)

WEBHOOK_PATH = "/webhook/telegram"


def webhook_secret() -> str:
    """سر يُشتق من توكن البوت بدل متغيّر بيئة جديد.

    القيد ٤: هذه القيمة لا تُطبع ولا تُعاد في أي رد — تُقارن فقط.
    """
    return hashlib.sha256(
        config.TELEGRAM_BOT_TOKEN.encode("utf-8")).hexdigest()[:32]


@app.get("/health")
def health() -> dict:
    """فحص صحة — يعرض حالة المفاتيح بـ SET/MISSING فقط (القيد ٤)."""
    try:
        db.ping()
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unreachable"
    return {"status": "ok", "database": database,
            "secrets": config.secrets_status(),
            "timezone": config.TIMEZONE,
            "test_time_scale": config.TEST_TIME_SCALE}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    # تليجرام يعيد المحاولة عند أي رمز غير 200، لذلك نرد 200 دائماً
    # ونتعامل مع الأخطاء داخلياً حتى لا تتكرر الرسالة على الزبون.
    if not hmac.compare_digest(x_telegram_bot_api_secret_token or "",
                               webhook_secret()):
        log.warning("رُفض طلب webhook: سر غير مطابق")
        return Response(status_code=200)

    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=200)

    try:
        _dispatch(update)
    except Exception as exc:  # noqa: BLE001
        log.exception("فشل في معالجة التحديث: %s", type(exc).__name__)
    return Response(status_code=200)


def _dispatch(update: dict) -> None:
    if "callback_query" in update:
        cq = update["callback_query"]
        frm = cq.get("from", {})
        chat = (cq.get("message") or {}).get("chat", {})
        user = User("telegram", str(frm.get("id")),
                    str(chat.get("id") or frm.get("id")))
        # إلزامي: يوقف دوران الزر عند الزبون فوراً.
        telegram_api.answer_callback_query(cq.get("id", ""))
        lang = db.get_language(user.platform, user.user_id)
        conversation.handle_callback(user, cq.get("data", ""), lang or "ar")
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    frm = msg.get("from", {})
    chat = msg.get("chat", {})
    user = User("telegram", str(frm.get("id")),
                str(chat.get("id") or frm.get("id")))

    if "voice" in msg or "audio" in msg:
        # المرحلة 5. حتى ذلك الحين نعامل الرسالة الصوتية كنص فارغ.
        conversation.handle_text(user, "", db.get_language(
            user.platform, user.user_id))
        return

    conversation.handle_text(user, msg.get("text", ""),
                             db.get_language(user.platform, user.user_id))
