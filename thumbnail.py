"""Monkey Unleashed thumbnails (1080x1920) in the channel style:
wooden logo sign, red "Quiz #N" badge, the monkey host, a wooden title sign, a yellow
"Can you guess...?" banner and the country flag, on top of the landmark photo.
   python thumbnail.py preview 0 5 14   -> writes previews/thumb_<i>.jpg for those quizzes"""
import io
import json
import math
import os
import sys

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
FONT_URLS = ["https://raw.githubusercontent.com/google/fonts/main/apache/luckiestguy/LuckiestGuy-Regular.ttf",
             "https://github.com/google/fonts/raw/main/apache/luckiestguy/LuckiestGuy-Regular.ttf"]
FONT_PATH = "fonts/LuckiestGuy-Regular.ttf"
FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FLAGS = {"Morocco": "ma", "USA": "us", "Canada": "ca", "UK": "gb", "Australia": "au", "Ireland": "ie",
         "New Zealand": "nz", "Jamaica": "jm", "South Africa": "za", "Egypt": "eg", "India": "in", "Nigeria": "ng",
         "Ghana": "gh", "Kenya": "ke", "Philippines": "ph", "Singapore": "sg"}
WOOD, WOOD_D, WOOD_L = (184, 116, 56), (92, 50, 20), (214, 150, 82)
RED, NAVY, YELLOW, WHITE, BROWN = (226, 28, 40), (22, 46, 150), (255, 214, 10), (255, 255, 255), (70, 36, 12)


def _usable(path):
    try:
        ImageFont.truetype(path, 20)
        return True
    except Exception:
        return False


def _font_file():
    if os.path.exists(FONT_PATH) and not _usable(FONT_PATH):
        os.remove(FONT_PATH)
    for url in FONT_URLS:
        if os.path.exists(FONT_PATH):
            break
        try:  # free Google font (Apache License 2.0), saved once into fonts/
            data = requests.get(url, timeout=30).content
            if data[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                os.makedirs("fonts", exist_ok=True)
                open(FONT_PATH, "wb").write(data)
                if not _usable(FONT_PATH):
                    os.remove(FONT_PATH)
        except Exception as e:
            print("Font download failed:", e)
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    print("Using the DejaVu font for thumbnails")
    return FALLBACK


FONT = None


def font(size):
    global FONT
    FONT = FONT or _font_file()
    return ImageFont.truetype(FONT, size)


def fit_font(d, text, max_w, size, min_size=40):
    while size > min_size and d.textlength(text, font=font(size)) > max_w:
        size -= 4
    return font(size)


def cartoon_text(d, xy, text, f, fill, inner=WHITE, outer=BROWN, iw=9, ow=17):
    """Thick sticker-style text: dark outline, white rim, coloured letters."""
    d.text(xy, text, font=f, fill=outer, anchor="mm", stroke_width=ow, stroke_fill=outer)
    d.text(xy, text, font=f, fill=fill, anchor="mm", stroke_width=iw, stroke_fill=inner)


def wood_sign(size, radius=46):
    w, h = size
    sign = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    wood = Image.new("RGBA", size, WOOD + (255,))
    g = ImageDraw.Draw(wood)
    for i, y in enumerate(range(8, h, 22)):  # planks and grain
        col = WOOD_L if i % 3 == 0 else (164, 100, 46)
        g.line([(0, y), (w, y + (i % 2) * 6)], fill=col, width=4)
    for y in range(h // 3, h, h // 3):
        g.line([(0, y), (w, y)], fill=WOOD_D, width=5)
    sign.paste(wood, (0, 0), mask)
    d = ImageDraw.Draw(sign)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=WOOD_D, width=12)
    d.rounded_rectangle([14, 14, w - 15, h - 15], radius=radius - 12, outline=WOOD_L, width=4)
    for x, y in ((34, 34), (w - 34, 34), (34, h - 34), (w - 34, h - 34)):  # nails
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(120, 120, 120), outline=(60, 60, 60), width=3)
    return sign


def shadow(layer, offset=(10, 14), blur=14, alpha=150):
    sh = Image.new("RGBA", (layer.width + 80, layer.height + 80), (0, 0, 0, 0))
    a = layer.split()[3].point(lambda p: p * alpha // 255)
    sh.paste((0, 0, 0, 255), (40 + offset[0], 40 + offset[1]), a)
    return sh.filter(ImageFilter.GaussianBlur(blur))


def paste(canvas, layer, xy, with_shadow=True):
    if with_shadow:
        canvas.alpha_composite(shadow(layer), (xy[0] - 40, xy[1] - 40))
    canvas.alpha_composite(layer, xy)


def crown(d, cx, cy, s=1.0):
    pts = [(-70, 40), (-80, -30), (-38, 5), (0, -50), (38, 5), (80, -30), (70, 40)]
    d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=(255, 200, 20), outline=BROWN, width=6)
    for x, y in ((-80, -30), (0, -50), (80, -30)):
        d.ellipse([cx + x * s - 11, cy + y * s - 11, cx + x * s + 11, cy + y * s + 11], fill=(255, 235, 120), outline=BROWN, width=4)


def bursts(d, cx, cy, r1, r2, angles, color=YELLOW, width=14):
    for a in angles:
        t = math.radians(a)
        d.line([(cx + r1 * math.cos(t), cy + r1 * math.sin(t)), (cx + r2 * math.cos(t), cy + r2 * math.sin(t))],
               fill=BROWN, width=width + 8)
        d.line([(cx + r1 * math.cos(t), cy + r1 * math.sin(t)), (cx + r2 * math.cos(t), cy + r2 * math.sin(t))],
               fill=color, width=width)


def get_flag(country):
    code = FLAGS.get(country)
    if not code:
        return None
    path = f"images/flag_{code}.png"
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    try:
        img = Image.open(io.BytesIO(requests.get(f"https://flagcdn.com/w640/{code}.png", timeout=30).content)).convert("RGBA")
        os.makedirs("images", exist_ok=True)
        img.save(path)
        return img
    except Exception as e:
        print("Flag download failed:", e)
        return None


def make_thumbnail(quiz, photo, host, path):
    """quiz: dict with number, country, thumb_title, thumb_hook. photo: PIL image or None. host: RGBA monkey."""
    # 1) bright, colourful landmark photo
    if photo is not None:
        bg = ImageOps.fit(photo.convert("RGB"), (W, H), Image.LANCZOS)
        bg = ImageEnhance.Color(bg).enhance(1.35)
        bg = ImageEnhance.Contrast(bg).enhance(1.1)
    else:
        bg = Image.new("RGB", (W, H), (70, 150, 220))
        ImageDraw.Draw(bg).rectangle([0, H // 2, W, H], fill=(214, 170, 110))
    canvas = bg.convert("RGBA")
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).rectangle([0, 0, W, H], fill=90)
    ImageDraw.Draw(vign).ellipse([-200, 200, W + 200, H - 200], fill=0)
    canvas = Image.composite(Image.new("RGBA", (W, H), (25, 12, 0, 255)), canvas, vign.filter(ImageFilter.GaussianBlur(120)))

    # 2) the monkey host, big, on the left
    m = host.copy()
    scale = 980 / m.height
    m = m.resize((int(m.width * scale), 980), Image.LANCZOS)
    if m.width > 760:
        m = m.resize((760, int(m.height * 760 / m.width)), Image.LANCZOS)
    paste(canvas, m, (max(-40, 380 - m.width // 2), 1420 - m.height))

    d = ImageDraw.Draw(canvas)
    # 3) the logo sign at the top
    sign = wood_sign((900, 330))
    sd = ImageDraw.Draw(sign)
    cartoon_text(sd, (450, 100), "Monkey", font(128), WHITE, inner=BROWN, outer=(40, 20, 5), iw=10, ow=14)
    cartoon_text(sd, (450, 215), "Unleashed", fit_font(sd, "Unleashed", 800, 132), YELLOW, inner=BROWN, outer=(40, 20, 5), iw=10, ow=14)
    paste(canvas, sign, (90, 70))
    strip = Image.new("RGBA", (640, 82), (0, 0, 0, 0))
    ImageDraw.Draw(strip).rounded_rectangle([0, 0, 639, 81], radius=22, fill=(250, 236, 200), outline=WOOD_D, width=6)
    ImageDraw.Draw(strip).text((320, 43), "Quizzes • Fun • Challenge", font=fit_font(ImageDraw.Draw(strip), "Quizzes • Fun • Challenge", 580, 46),
                               fill=BROWN, anchor="mm")
    paste(canvas, strip, (220, 365))
    crown(d, 300, 72, 0.75)

    # 4) the red "Quiz #N" badge, tilted
    badge = Image.new("RGBA", (500, 360), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.ellipse([10, 10, 490, 350], fill=BROWN)
    bd.ellipse([22, 22, 478, 338], fill=WHITE)
    bd.ellipse([38, 38, 462, 322], fill=RED)
    bd.ellipse([70, 50, 430, 150], fill=(240, 80, 80))
    cartoon_text(bd, (250, 125), "Quiz", font(110), WHITE, inner=BROWN, outer=BROWN, iw=6, ow=9)
    cartoon_text(bd, (250, 245), f"#{quiz['number']}", fit_font(bd, f"#{quiz['number']}", 380, 140), YELLOW,
                 inner=BROWN, outer=BROWN, iw=7, ow=11)
    badge = badge.rotate(7, resample=Image.BICUBIC, expand=True)
    bx, by = W - badge.width - 10, 500
    bursts(d, bx + badge.width // 2, by + badge.height // 2, 255, 320, (-150, -165, 180, 20, 35, 50))
    paste(canvas, badge, (bx, by))

    # 5) the title sign at the bottom (two lines: red, then blue)
    lines = (quiz.get("thumb_title") or f"{quiz['country']}|Week").split("|")
    sign = wood_sign((980, 330 if len(lines) > 1 else 220))
    sd = ImageDraw.Draw(sign)
    colours = [RED, NAVY]
    for i, text in enumerate(lines[:2]):
        y = 92 + i * 140 if len(lines) > 1 else 110
        cartoon_text(sd, (490, y), text, fit_font(sd, text, 860, 132), colours[i % 2])
    paste(canvas, sign, (50, 1330))

    # 6) flag (bottom left) and the yellow "Can you guess...?" banner (bottom right)
    flag = get_flag(quiz["country"])
    if flag is not None:
        flag.thumbnail((330, 220))
        framed = Image.new("RGBA", (flag.width + 24, flag.height + 24), WHITE + (255,))
        framed.paste(flag, (12, 12), flag)
        ImageDraw.Draw(framed).rectangle([0, 0, framed.width - 1, framed.height - 1], outline=BROWN, width=5)
        framed = framed.rotate(8, resample=Image.BICUBIC, expand=True)
        paste(canvas, framed, (40, 1680))
    hook = (quiz.get("thumb_hook") or "Can you guess|the answer?").split("|")
    ban = Image.new("RGBA", (620, 250), (0, 0, 0, 0))
    bnd = ImageDraw.Draw(ban)
    bnd.polygon([(20, 30), (600, 0), (610, 220), (0, 250)], fill=BROWN)
    bnd.polygon([(30, 40), (588, 12), (598, 208), (12, 236)], fill=(255, 228, 40))
    bnd.text((305, 82), hook[0], font=fit_font(bnd, hook[0], 520, 66), fill=NAVY, anchor="mm")
    if len(hook) > 1:
        bnd.text((305, 168), hook[1], font=fit_font(bnd, hook[1], 540, 88), fill=RED, anchor="mm",
                 stroke_width=3, stroke_fill=(150, 10, 20))
    ban = ban.rotate(-4, resample=Image.BICUBIC, expand=True)
    paste(canvas, ban, (W - ban.width - 20, H - ban.height - 30))

    canvas.convert("RGB").save(path, quality=92)
    return path


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "preview":
    import make_videos as mv
    quizzes = json.load(open("quizzes.json"))
    os.makedirs("previews", exist_ok=True)
    host = mv.monkey_layer()
    for i in [int(x) for x in sys.argv[2:]] or [0]:
        q = dict(quizzes[i], number=100 + i)
        photo, _ = mv.landmark_photo(q)
        print("preview", i, make_thumbnail(q, photo, host, f"previews/thumb_{i}.jpg"))
