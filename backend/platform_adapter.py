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


def texts_default() -> str:
    import texts
    return texts.DEFAULT_LANG


class ButtonLimitError(ValueError):
    """يُرفع عند تجاوز حد الخيارات — خطأ برمجي لا يُخفى."""


@dataclass
class User:
    """هوية الزبون مستقلة عن المنصة — SPEC 11: المفتاح (platform, user_id).

    voice: الرسالة الواردة كانت صوتية، فالرد يكون صوتاً أيضاً (SPEC 9).
    voiced: أُرسل الرد الصوتي في هذه النوبة — نمنع تكراره إن أرسل
            منطق المحادثة أكثر من رسالة واحدة.
    """
    platform: str
    user_id: str
    chat_id: str | None = None
    voice: bool = False
    voiced: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.platform, self.user_id)

    def __hash__(self) -> int:
        # الهوية هي (المنصة، المعرّف) وحدها. حقلا النوبة الصوتية متغيّران
        # ولا يدخلان في الهوية، وإلا تغيّر التجزيء أثناء الاستعمال.
        return hash(self.key)


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

    def send_link(self, user: User, text: str, label: str, url: str) -> None:
        """زر يفتح رابطاً خارجياً. يقابله في واتساب زر cta_url."""
        raise NotImplementedError


class TelegramAdapter(BaseAdapter):
    platform = "telegram"

    # SPEC — تأكيد بصري للزبون: نستعمل لوحة الرد لا الأزرار الداخلية.
    # تليجرام لا يسمح لبوت أن يرسل رسالة باسم الزبون، والطريقة الوحيدة
    # لظهور اختياره كفقاعة على يمين الشاشة هي أن يضغط زراً يُرسل نصه
    # رسالةً منه فعلاً. لذلك نخزّن خريطة (نص الزر ← الإجراء) في حالة
    # المستخدم، ونترجم الرسالة الواردة إلى الإجراء المقابل.
    @staticmethod
    def _markup(buttons, nav):
        rows = [[{"text": label}] for label, _ in buttons]
        if nav:
            rows.append([{"text": label}
                         for label, _ in nav[:MAX_QUICK_BUTTONS]])
        return {"keyboard": rows, "resize_keyboard": True,
                "one_time_keyboard": False, "is_persistent": True}

    @staticmethod
    def _remember(user: User, buttons, nav) -> None:
        """يحفظ خريطة نصوص الأزرار لهذه الشاشة ليُترجم ردّ الزبون."""
        import db
        mapping = {label: data for label, data in list(buttons) + list(nav or [])}
        st = db.get_user_state(user.platform, user.user_id) or {}
        data = dict(st.get("data") or {})
        data["_kb"] = mapping
        db.save_user_state(user.platform, user.user_id, data=data)

    def _maybe_voice(self, user: User, text: str) -> None:
        """SPEC 9: صوت داخل ← صوت خارج.

        يُرسل الصوت أولاً ثم النص والأزرار دائماً، لأن الأزرار لا تُنقر
        من الصوت. وإن فشل التوليد نُكمل نصاً بلا إزعاج الزبون.
        """
        if not user.voice or user.voiced:
            return
        user.voiced = True
        import db as _db
        import voice
        lang = (_db.get_language(user.platform, user.user_id)
                or texts_default())
        audio = voice.render(text, lang)
        if audio:
            telegram_api.send_voice(user.chat_id or user.user_id, audio)

    def send_text(self, user: User, text: str) -> None:
        self._maybe_voice(user, text)
        telegram_api.send_message(user.chat_id or user.user_id, text)

    def send_buttons(self, user: User, text: str, buttons, nav=None) -> None:
        _validate(buttons)
        self._maybe_voice(user, text)
        if buttons or nav:
            self._remember(user, buttons, nav)
        telegram_api.send_message(user.chat_id or user.user_id, text,
                                  self._markup(buttons, nav))

    def edit_buttons(self, user: User, message_id, text: str,
                     buttons, nav=None) -> None:
        """يعدّل الرسالة نفسها بدل إرسال رسالة جديدة — تصفّح أنظف."""
        _validate(buttons)
        telegram_api.edit_message_text(user.chat_id or user.user_id, message_id,
                                       text, self._markup(buttons, nav))

    def send_link(self, user: User, text: str, label: str, url: str) -> None:
        telegram_api.send_message(
            user.chat_id or user.user_id, text,
            {"inline_keyboard": [[{"text": label, "url": url}]]})

    def send_voice(self, user: User, audio_bytes: bytes, caption: str = "") -> None:
        telegram_api.send_voice(user.chat_id or user.user_id, audio_bytes,
                                caption)


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

    def send_link(self, user: User, text: str, label: str, url: str) -> None:
        raise NotImplementedError("واتساب غير مفعّل بعد")

    def send_voice(self, user: User, audio_bytes: bytes, caption: str = "") -> None:
        raise NotImplementedError("واتساب غير مفعّل بعد")


ADAPTERS = {"telegram": TelegramAdapter()}


def get(platform: str = "telegram") -> BaseAdapter:
    return ADAPTERS[platform]
