# -*- coding: utf-8 -*-
"""نداءات Telegram Bot API مباشرة عبر httpx — بدون أي مكتبة bot framework."""
import logging

import httpx

import config

log = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot%s" % config.TELEGRAM_BOT_TOKEN
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _call(method: str, **payload) -> dict:
    """ينادي الـ API ويعيد النتيجة.

    القيد ٤: التوكن جزء من الرابط، لذلك لا يُطبع الرابط أبداً في اللوغ —
    نطبع اسم الدالة فقط.
    """
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post("%s/%s" % (_BASE, method), json=payload)
        data = r.json()
        if not data.get("ok"):
            log.error("telegram %s فشل: %s", method, data.get("description"))
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("telegram %s استثناء: %s", method, type(exc).__name__)
        return {"ok": False}


def send_message(chat_id, text: str, reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", **payload)


def edit_message_text(chat_id, message_id, text: str,
                      reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("editMessageText", **payload)


def answer_callback_query(callback_id: str, text: str = "") -> dict:
    """يوقف دوران الزر عند الزبون. إلزامي بعد كل ضغطة."""
    return _call("answerCallbackQuery", callback_query_id=callback_id, text=text)


def send_chat_action(chat_id, action: str = "typing") -> dict:
    return _call("sendChatAction", chat_id=chat_id, action=action)


def get_me() -> dict:
    return _call("getMe")


def set_webhook(url: str, secret_token: str | None = None) -> dict:
    payload = {"url": url, "allowed_updates": ["message", "callback_query"]}
    if secret_token:
        payload["secret_token"] = secret_token
    return _call("setWebhook", **payload)


def delete_webhook() -> dict:
    return _call("deleteWebhook")


def get_webhook_info() -> dict:
    return _call("getWebhookInfo")


# ------------------------------------------------------------- الصوت
def get_file(file_id: str) -> dict:
    """يعيد بيانات الملف بما فيها file_path اللازم للتنزيل."""
    return _call("getFile", file_id=file_id)


def download_file(file_path: str) -> bytes:
    """ينزّل ملفاً من خوادم تليجرام.

    القيد ٤: الرابط يحوي التوكن، فلا يُطبع ولا يُسجَّل في أي حال.
    """
    url = "https://api.telegram.org/file/bot%s/%s" % (
        config.TELEGRAM_BOT_TOKEN, file_path)
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
            r = c.get(url)
        if r.status_code != 200:
            log.error("تنزيل ملف تليجرام فشل برمز %s", r.status_code)
            return b""
        return r.content
    except Exception as exc:  # noqa: BLE001
        log.error("تنزيل ملف تليجرام استثناء: %s", type(exc).__name__)
        return b""


def send_voice(chat_id, audio: bytes, caption: str = "") -> dict:
    """يرسل رسالة صوتية حقيقية. الصيغة ogg/opus وإلا عرضها تليجرام كمرفق."""
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
            r = c.post("%s/sendVoice" % _BASE, data=data,
                       files={"voice": ("reply.ogg", audio, "audio/ogg")})
        out = r.json()
        if not out.get("ok"):
            log.error("sendVoice فشل: %s", out.get("description"))
        return out
    except Exception as exc:  # noqa: BLE001
        log.error("sendVoice استثناء: %s", type(exc).__name__)
        return {"ok": False}
