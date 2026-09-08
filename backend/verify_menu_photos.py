# -*- coding: utf-8 -*-
"""تحقق عرض المنيو صوراً — SPEC 7.5.

الفحص ليس «هل تُرسل صور» فقط، بل ثلاثة أمور معاً:
  1. الأصول موجودة وسليمة وضمن ميزانية الحجم والصيغة التي يقبلها تليجرام.
  2. كل زر يرسل صور فئته هو لا فئة أخرى، بالترتيب الصحيح.
  3. النص لم يُحذف: الأصناف وأسعارها ما زالت تُقرأ من القاعدة، فالنموذج
     يجيب عن الأسعار والأدمن يراها. التغيير عرضٌ لا حذف.
"""
import sys
from pathlib import Path, PurePosixPath

import conversation
import db
import platform_adapter
import texts
from platform_adapter import User

UID = "__verifymenu__"
ok = True
sent: list = []


def check(passed: bool, line: str) -> None:
    global ok
    ok = ok and passed
    print("  %s %s" % ("PASS" if passed else "FAIL", line))


class Fake(platform_adapter.BaseAdapter):
    platform = "telegram"

    def send_text(self, user, text, plain=False):
        sent.append({"text": text, "buttons": [], "album": None})

    def send_buttons(self, user, text, buttons, nav=None):
        platform_adapter._validate(buttons)
        sent.append({"text": text,
                     "buttons": [b[1] for b in buttons] + [
                         n[1] for n in (nav or [])],
                     "album": None})

    def send_link(self, user, text, label, url):
        sent.append({"text": text, "buttons": [], "album": None})

    def send_album(self, user, paths, caption=""):
        sent.append({"text": caption, "buttons": [],
                     "album": [p.name for p in paths]})


def press(user, data, lang="ar") -> list:
    sent.clear()
    conversation.handle_callback(user, data, lang)
    return list(sent)


GROUPS = ("food", "drinks", "shisha")
MAX_KB = 400
# تليجرام يقبل حتى 10 صور في الألبوم الواحد.
MAX_ALBUM = 10


def main() -> int:                                    # noqa: C901
    print("=" * 64)
    print("تحقق عرض المنيو صوراً — SPEC 7.5")
    print("=" * 64)

    platform_adapter.ADAPTERS["telegram"] = Fake()
    user = User("telegram", UID, UID)

    # -------------------------------- 0) هل تصل الصور إلى الحاوية؟
    # هذا الفحص هو الذي كان غائباً. الستّة والخمسون فحصاً الباقية نجحت
    # كلها بينما الزرّ في الإنتاج يردّ «الصور غير متوفرة»: كانت الصور في
    # جذر المستودع، وسياقُ بناء Docker هو backend/ وحده، فلم تدخل
    # الصورة أصلاً. ومع ذلك مرّت الفحوص لأنها تقرأ شجرة التطوير لا
    # الحاوية. فالفحص هنا يحاكي ما ينسخه Docker فعلاً.
    print("\n0) وصول الصور إلى صورة Docker")
    import shutil
    import tempfile

    context = Path(__file__).resolve().parent          # سياق البناء
    check((context / "Dockerfile").is_file(),
          "سياق البناء هو %s وفيه Dockerfile" % context.name)
    check(conversation.MENU_PHOTOS.is_relative_to(context),
          "مسار الصور داخل سياق البناء: %s"
          % conversation.MENU_PHOTOS.relative_to(context.parent))

    ignore = context / ".dockerignore"
    patterns = []
    if ignore.is_file():
        patterns = [ln.strip() for ln in
                    ignore.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]

    def excluded(rel: str) -> bool:
        """هل يستبعد .dockerignore هذا المسار؟ — مطابقة الأنماط المستعملة."""
        import fnmatch
        for pattern in patterns:
            clean = pattern.rstrip("/")
            if rel == clean or rel.startswith(clean + "/"):
                return True
            if fnmatch.fnmatch(rel, clean) or fnmatch.fnmatch(
                    PurePosixPath(rel).name, clean):
                return True
        return False

    # نبني شجرةً كما ينسخها COPY . . ثم نستورد منها المسار
    staged, skipped = 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "app"                        # WORKDIR /app
        for src in context.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(context).as_posix()
            if excluded(rel):
                skipped += 1
                continue
            dest = app / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            staged += 1

        # المسار كما يحسبه الكود من داخل الحاوية: parent لا parent.parent
        in_container = (app / "conversation.py").resolve().parent / "assets" \
            / "menu"
        check(in_container.is_dir(),
              "مجلد الصور موجود داخل الحاوية: /app/assets/menu")
        for group in GROUPS:
            found = sorted((in_container / group).glob("*.jpg"))
            here = conversation.menu_photos(group)
            check(len(found) == len(here) and found,
                  "  %s: %d صورة وصلت الحاوية (محلياً %d)"
                  % (group, len(found), len(here)))
    print("  نُسخ %d ملفاً، واستُبعد %d بـ.dockerignore" % (staged, skipped))

    # وأصول الصور لا تدخل — نسخة مكرّرة بلا فائدة في الإنتاج
    check(excluded("assets/menu/original/menu-01.jpg"),
          "والأصول مستبعدة، فلا تتضاعف الصورة")

    # ------------------------------------------------- 1) الأصول
    print("\n1) ملفات الصور")
    from PIL import Image

    total = 0.0
    for group in GROUPS:
        photos = conversation.menu_photos(group)
        check(bool(photos), "%s: فيها %d صورة" % (group, len(photos)))
        check(len(photos) <= MAX_ALBUM,
              "  وعددها ضمن حد الألبوم (%d ≤ %d)" % (len(photos), MAX_ALBUM))
        for path in photos:
            size = path.stat().st_size / 1024
            total += size
            image = Image.open(path)
            # تليجرام يعامل WebP كملصق لا كصورة، فالصيغة هنا JPEG حتماً.
            fine = (image.format == "JPEG" and size <= MAX_KB
                    and max(image.size) <= 1600)
            check(fine, "  %-30s %4dx%-4d %5.0f KB %s"
                  % (path.name, image.width, image.height, size,
                     image.format))
        check(photos == sorted(photos),
              "  والترتيب ترتيب أسماء الملفات — ترتيب المنيو الورقي")
    print("  المجموع: %.0f KB" % total)

    # ------------------------------------- 2) شاشة المنيو: ثلاثة أزرار
    print("\n2) زر المنيو -> ثلاث فئات")
    msgs = press(user, "M")
    check(len(msgs) == 1, "رسالة واحدة")
    targets = msgs[0]["buttons"]
    for want in ("M:g:food", "M:g:drinks", "M:g:shisha"):
        check(want in targets, "  فيها زر %s" % want)
    check(sum(1 for t in targets if t.startswith("M:g:")) == 3,
          "  ولا فئة رابعة")

    # -------------------------------------- 3) كل زر يرسل صور فئته
    print("\n3) كل فئة ترسل صورها هي")
    for group in GROUPS:
        msgs = press(user, "M:g:%s" % group)
        albums = [m for m in msgs if m["album"]]
        check(len(albums) == 1, "%s: ألبوم واحد" % group)
        if not albums:
            continue
        names = albums[0]["album"]
        expected = [p.name for p in conversation.menu_photos(group)]
        check(names == expected, "  الصور وترتيبها: %s" % names)
        check(albums[0]["text"] == texts.t("ar", "menu_photos_%s" % group),
              "  والتعليق تعليق الفئة: «%s»" % albums[0]["text"])

        # لا تتسرّب صورة فئة إلى أخرى
        for other in GROUPS:
            if other == group:
                continue
            leaked = set(names) & {
                p.name for p in conversation.menu_photos(other)}
            check(not leaked, "  ولا صورة من %s" % other)

        # وبعد الصور: طريق للأمام لا طريق مسدود
        after = [m for m in msgs if not m["album"]]
        check(bool(after), "  وبعدها رسالة فيها أزرار")
        if after:
            check("B" in after[-1]["buttons"], "  فيها زر الحجز")
            check("H" in after[-1]["buttons"], "  وزر الرئيسية")

    # ---------------------------------- 4) الإنجليزية تعليقها إنجليزي
    print("\n4) اللغة")
    msgs = press(user, "M:g:food", "en")
    albums = [m for m in msgs if m["album"]]
    check(albums and albums[0]["text"] == texts.t("en", "menu_photos_food"),
          "التعليق بالإنجليزية: «%s»"
          % (albums[0]["text"] if albums else "—"))

    # ------------------------------- 5) النص لم يُحذف — عرضٌ لا حذف
    print("\n5) الأصناف وأسعارها ما زالت في القاعدة")
    items = db.all_menu_items()
    check(len(items) == 124, "عدد الأصناف %d" % len(items))
    check(all(i.get("price") is not None for i in items),
          "ولكلٍّ منها سعر")

    blob = []
    for cat in conversation._tree().values():
        for sub_slug in cat["subs"]:
            page = 0
            while True:
                built = conversation.build_items_screen("ar", sub_slug, page)
                if not built:
                    break
                blob.append(built["text"])
                page += 1
                if page >= built["pages"]:
                    break
    text = "\n".join(blob)
    missing = [i["name_ar"] for i in items if i["name_ar"] not in text]
    check(not missing, "وكلها ما زالت تُرسم نصّاً بأسعارها%s"
          % ("" if not missing else " — ناقص %s" % missing[:3]))
    check(texts.t("ar", "tax_note") in text, "مع التنويه الضريبي")

    # والنموذج يبني سياقه من نفس البيانات — الدليل العملي أنها حيّة
    # لا محفوظة للزينة. hasattr وحدها فحصٌ لا يفحص، فنستدعي المصدر.
    import ai
    block = ai._menu_block()
    absent = [i["name_ar"] for i in items if i["name_ar"] not in block][:3]
    check(not absent, "وسياق النموذج يحمل الأصناف بأسعارها%s"
          % ("" if not absent else " — ناقص %s" % absent))

    # ------------------------------- 6) غياب الصور لا يترك شاشة فارغة
    print("\n6) غياب الصور")
    real = conversation.MENU_PHOTOS
    conversation.MENU_PHOTOS = Path(real).parent / "__no_such_dir__"
    try:
        msgs = press(user, "M:g:food")
        check(not any(m["album"] for m in msgs), "لا ألبوم")
        check(any(texts.t("ar", "menu_photos_missing") in (m["text"] or "")
                  for m in msgs),
              "بل اعتذار يدلّ على السؤال الحر بدل شاشة فارغة")
    finally:
        conversation.MENU_PHOTOS = real

    db.client().table("user_state").delete().eq("user_id", UID).execute()
    print("\n" + "=" * 64)
    print("النتيجة: %s" % ("نجح كل الفحوصات" if ok else "في فحوصات فاشلة"))
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
