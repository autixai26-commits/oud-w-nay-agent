# -*- coding: utf-8 -*-
"""يضغط صور الصالات للويب — CONSTRAINTS القيد ٣.

    python backend/compress_images.py

يقرأ الأصول من web/images/original/ ويكتب نسختين لكل صالة في web/images/:
WebP أساسي وJPG احتياطي، بعرض أقصى 1600 بكسل والارتفاع بالتناسب.

استثناء مثبّت: hall_outdoor أصلها 1449 بكسل فقط، تُستخدم بعرضها الأصلي
وممنوع تكبيرها. قرار المالك، مقفل.
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "images" / "original"
OUT = ROOT / "web" / "images"

MAX_WIDTH = 1600
QUALITY = 85          # نبدأ من 85 ونعاين بصرياً قبل النزول (القيد ٣)

HALLS = {
    "hall_outdoor": "hall_outdoor.png",
    "hall_main": "hall_main.png",
    "hall_narrow": "hall_narrow.jpg",
}


def main() -> int:
    if not SRC.is_dir():
        print("مجلد الأصول غير موجود: %s" % SRC)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    print("%-14s %-13s %-13s %9s %9s %7s" %
          ("الصالة", "الأصل", "الناتج", "WebP", "JPG", "التوفير"))
    print("-" * 72)

    for name, filename in HALLS.items():
        path = SRC / filename
        if not path.exists():
            print("%-14s الأصل مفقود: %s" % (name, filename))
            return 1

        img = Image.open(path)
        src_size = path.stat().st_size
        w, h = img.size

        # لا تكبير أبداً: العرض الهدف هو الأصغر بين 1600 والعرض الأصلي.
        target_w = min(MAX_WIDTH, w)
        target_h = round(h * target_w / w)
        resized = img.convert("RGB").resize((target_w, target_h),
                                            Image.LANCZOS)

        webp_path = OUT / ("%s.webp" % name)
        jpg_path = OUT / ("%s.jpg" % name)
        resized.save(webp_path, "WEBP", quality=QUALITY, method=6)
        resized.save(jpg_path, "JPEG", quality=QUALITY,
                     optimize=True, progressive=True)

        webp_size = webp_path.stat().st_size
        jpg_size = jpg_path.stat().st_size
        note = "" if target_w == MAX_WIDTH else "  (بعرضها الأصلي، بلا تكبير)"
        print("%-14s %-13s %-13s %8.1fK %8.1fK %6.1f%%%s" % (
            name, "%dx%d" % (w, h), "%dx%d" % (target_w, target_h),
            webp_size / 1024, jpg_size / 1024,
            100 * (1 - webp_size / src_size), note))

    print("-" * 72)
    print("النسب: %s" % " · ".join(
        "%s %.2f" % (n, Image.open(OUT / ("%s.jpg" % n)).size[0]
                     / Image.open(OUT / ("%s.jpg" % n)).size[1])
        for n in HALLS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
