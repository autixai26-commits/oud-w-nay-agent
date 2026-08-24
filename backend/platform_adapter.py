# -*- coding: utf-8 -*-
"""طبقة تجريد المنصة — SPEC 11.

منطق المحادثة يستدعي هذه الواجهة فقط، ولا يعرف شيئاً عن تليجرام.
عند إضافة واتساب لاحقاً يكفي كتابة WhatsAppAdapter دون لمس conversation.py.

قيود واتساب المستقبلية محترمة من الآن (SPEC 11):
  * لا يزيد أي مستوى أزرار عن 10 خيارات.
  * لا تزيد الأزرار السريعة عن 3 في الرسالة الواحدة — ما زاد يصير قائمة.
تُفرض القاعدتان هنا في الطبقة المشتركة، لا في كود تليجرام، حتى تنطبقا
على أي منصة قادمة تلقائياً.
"""
from dataclasses import dataclass

import telegram_api

MAX_OPTIONS_PER_LEVEL = 10   # SPEC 7.1 و 11
MAX_QUICK_BUTTONS = 3        # SPEC 11 — ما زاد يُعرض كقائمة


class ButtonLimitError(ValueError):
    """يُرفع عند تجاوز حد الخيارات — خطأ برمجي لا يُخفى."""


@dataclass(frozen=True)
class User:
    """هوية الزبون مستقلة عن المنصة — SPEC 11: المفتاح (platform, user_id)."""
    platform: str
    user_id: str
    chat_id: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.platform, self.user_id)


def _validate(buttons: list[tuple[str, str]]) -> None:
    if len(buttons) > MAX_OPTIONS_PER_LEVEL:
        raise ButtonLimitError(
            "مستوى فيه %d خيار والحد %d (SPEC 7.1) — قسّمه لصفحات."
            % (len(buttons), MAX_OPTIONS_PER_LEVEL))


class BaseAdapter:
    platform = "base"

    def send_text(self, user: User, text: str) -> None:
        raise NotImplementedError

    def send_buttons(self, user: User, text: str,
                     buttons: list[tuple[str, str]],
                     nav: list[tuple[str, str]] | None = None) -> None:
        """buttons: قائمة (نص الزر، callback_data). nav: صف تنقّل اختياري."""
        raise NotImplementedError

    def send_voice(self, user: User, audio_bytes: bytes,
                   caption: str = "") -> None:
        raise NotImplementedError


class TelegramAdapter(BaseAdapter):
    platform = "telegram"

    @staticmethod
    def _markup(buttons, nav):
        rows = [[{"text": label, "callback_data": data}] for label, data in buttons]
        if nav:
            # صف التنقّل يوضع أفقياً وبحد أقصى 3 — يقابل الأزرار السريعة بواتساب.
            rows.append([{"text": label, "callback_data": data}
                         for label, data in nav[:MAX_QUICK_BUTTONS]])
        return {"inline_keyboard": rows}

    def send_text(self, user: User, text: str) -> None:
        telegram_api.send_message(user.chat_id or user.user_id, text)

    def send_buttons(self, user: User, text: str, buttons, nav=None) -> None:
        _validate(buttons)
        telegram_api.send_message(user.chat_id or user.user_id, text,
                                  self._markup(buttons, nav))

    def edit_buttons(self, user: User, message_id, text: str,
                     buttons, nav=None) -> None:
        """يعدّل الرسالة نفسها بدل إرسال رسالة جديدة — تصفّح أنظف."""
        _validate(buttons)
        telegram_api.edit_message_text(user.chat_id or user.user_id, message_id,
                                       text, self._markup(buttons, nav))

    def send_voice(self, user: User, audio_bytes: bytes, caption: str = "") -> None:
        # المرحلة 5.
        raise NotImplementedError("الصوت يُنفَّذ في المرحلة 5")


class WhatsAppAdapter(BaseAdapter):
    """هيكل فارغ — يُنفَّذ عند تفعيل واتساب.

    ملاحظة إلزامية (SPEC 11): عند التشغيل بوضع Coexistence، يجب إضافة
    منطق يوقف البوت 30 دقيقة عن أي زبون ردّ عليه موظف يدوياً من التطبيق،
    وإلا تداخل رد البوت مع رد الموظف على نفس المحادثة.

    فروق التنفيذ المتوقّعة عن تليجرام:
      * ≤3 أزرار سريعة في الرسالة؛ ما زاد يُرسل كـ interactive list.
      * القائمة الواحدة ≤10 صفوف — وهو نفس الحد المفروض هنا أصلاً.
      * لا يوجد تعديل رسالة سابقة، فكل خطوة رسالة جديدة.
    """
    platform = "whatsapp"

    def send_text(self, user: User, text: str) -> None:
        raise NotImplementedError("واتساب غير مفعّل بعد")

    def send_buttons(self, user: User, text: str, buttons, nav=None) -> None:
        _validate(buttons)
        raise NotImplementedError("واتساب غير مفعّل بعد")

    def send_voice(self, user: User, audio_bytes: bytes, caption: str = "") -> None:
        raise NotImplementedError("واتساب غير مفعّل بعد")


ADAPTERS = {"telegram": TelegramAdapter()}


def get(platform: str = "telegram") -> BaseAdapter:
    return ADAPTERS[platform]
