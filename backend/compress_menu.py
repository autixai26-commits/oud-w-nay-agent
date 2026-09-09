# -*- coding: utf-8 -*-
"""يجهّز صور المنيو لتليجرام — CONSTRAINTS القيد ٣ بروح المرحلة 3.

    python backend/compress_menu.py

يقرأ الأصول من backend/assets/menu/original/ وفق MAPPING أدناه، ويكتب الصور
الجاهزة في backend/assets/menu/{food,drinks,shisha}/ بترقيم يحفظ ترتيب المنيو.

**JPEG لا WebP.** تليجرام يعامل WebP كملصق (sticker) لا كصورة، فـ
sendPhoto وsendMediaGroup يرفضانه أو يعرضانه خطأً. صور الموقع WebP لأن
المتصفّح يدعمها، وهذه JPEG لأن المستهلك مختلف.

والضغط هنا **ميزانية لا إعادة ترميز إجبارية**: ما كان تحت الحدّ أصلاً
يُنسخ كما هو. الأصل صور نصّية عربية مضغوطة سلفاً، وإعادة ترميزها بجودة
85 توفّر ٧٪ فقط مقابل جيل ضياع إضافي (PSNR ‏44–47 dB) — خسارةٌ في وضوح
الحروف بلا مكسب يُذكر. أما ما تجاوز الحدّ فيُصغَّر ويُعاد ترميزه.
"""
import shutil
import sys
from pathlib import Path

from PIL import Image

# داخل backend/ لا في جذر المستودع: سياق بناء Docker هو backend/ وحده.
BASE = Path(__file__).resolve().parent / "assets" / "menu"
SRC = BASE / "original"
OUT = BASE

MAX_SIDE = 1600         # أطول ضلع؛ تليجرام يعرض حتى 1280 ويكبّر عند الزوم
MAX_KB = 400            # ميزانية الصورة الواحدة
# أفضل جودة تسع الميزانية، لا جودة ثابتة. المصدر قد يكون PNG بلا فقد،
# وتحويله بجودة 85 يترك حلقات حول الحروف العربية الدقيقة بلا داعٍ ما
# دامت الميزانية تتّسع لأعلى. نبدأ من الأعلى وننزل حتى يدخل الحدّ.
QUALITY_LADDER = (95, 92, 88, 85, 80, 75)

# ترتيب المنيو مقصود: الشوربات والسلطات فالمقبلات الباردة فالساخنة
# فالأطباق الرئيسية فالبحريات فالحلويات — كما يُقرأ المنيو الورقي.
MAPPING = {
    "food": [
        ("menu-02.png", "01-soups-salads"),
        ("menu-01.png", "02-cold-appetizers"),
        ("menu-04.png", "03-hot-appetizers"),
        ("menu-03.png", "04-main-dishes"),
        ("menu-05.png", "05-seafood"),
        ("menu-06.png", "06-desserts"),
    ],
    "drinks": [
        ("menu-08.png", "01-hot-drinks"),
        ("menu-07.png", "02-cold-drinks-juices"),
    ],
    "shisha": [
        ("menu-09.png", "01-hookah"),
    ],
}


def prepare(src: Path, dest: Path) -> tuple:
    """يعيد (الحجم بالكيلوبايت، الجودة المستعملة أو None إن نُسخت)."""
    image = Image.open(src)
    too_big = max(image.size) > MAX_SIDE
    too_heavy = src.stat().st_size / 1024 > MAX_KB

    if not too_big and not too_heavy and src.suffix.lower() in (".jpg",
                                                                ".jpeg"):
        shutil.copyfile(src, dest)
        return dest.stat().st_size / 1024, None

    # JPEG بلا قناة شفافية، فتُسطَّح على أبيض لا تُسقَط: إسقاطها يحوّل
    # الشفاف إلى أسود. وخلفية المنيو فاتحة أصلاً فالأبيض هو الصحيح.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    else:
        image = image.convert("RGB")

    # لا تكبير: التكبير لا يضيف معلومة، ويكبّر الحجم ويوهم بدقّة ليست فيه.
    if too_big:
        ratio = MAX_SIDE / max(image.size)
        image = image.resize(
            (round(image.width * ratio), round(image.height * ratio)),
            Image.LANCZOS)

    for quality in QUALITY_LADDER:
        image.save(dest, "JPEG", quality=quality, optimize=True,
                   progressive=True)
        if dest.stat().st_size / 1024 <= MAX_KB:
            return dest.stat().st_size / 1024, quality
    return dest.stat().st_size / 1024, QUALITY_LADDER[-1]


def main() -> int:
    if not SRC.is_dir():
        print("مجلد الأصول غير موجود: %s" % SRC)
        return 1

    print("%-8s %-26s %8s %10s" % ("الفئة", "الملف", "الحجم", "المعالجة"))
    print("-" * 58)
    total, missing = 0.0, []
    for group, files in MAPPING.items():
        target = OUT / group
        target.mkdir(parents=True, exist_ok=True)
        for source_name, out_name in files:
            source = SRC / source_name
            if not source.is_file():
                missing.append(str(source))
                continue
            dest = target / ("%s.jpg" % out_name)
            size, quality = prepare(source, dest)
            total += size
            print("%-8s %-26s %6.0f KB %10s"
                  % (group, dest.name, size,
                     "جودة %d" % quality if quality else "نُسخت كما هي"))

    print("-" * 58)
    print("المجموع: %.0f KB في %d صورة"
          % (total, sum(len(v) for v in MAPPING.values())))
    if missing:
        print("\nأصول مفقودة:")
        for path in missing:
            print("  %s" % path)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
