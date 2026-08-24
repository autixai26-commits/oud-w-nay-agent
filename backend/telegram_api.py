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
