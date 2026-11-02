"""Makes today's Monkey Unleashed quiz videos into the out/ folder."""
import json
import os
import random
import datetime
import io
import subprocess

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
OUT = "out"
LETTERS = "ABCD"
COUNTDOWN = 5
INTRO = 2.5
MIN_LEN, MAX_LEN = 20, 40  # video length in seconds


def font(size, serif=False):
    name = "DejaVuSerif-Bold.ttf" if serif else "DejaVuSans-Bold.ttf"
    return ImageFont.truetype(FONT_DIR + name, size)


def parchment(seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (226, 204, 156))
    noise = Image.effect_noise((W, H), 40).convert("RGB")
    img = Image.blend(img, noise, 0.08)
    d = ImageDraw.Draw(img)
    # faint old-map lines and coastlines
    for x in range(0, W, 135):
        d.line([(x, 0), (x, H)], fill=(196, 170, 120), width=2)
    for y in range(0, H, 135):
        d.line([(0, y), (W, y)], fill=(196, 170, 120), width=2)
    for _ in range(6):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        pts = []
        for _ in range(40):
            x += rnd.randint(-45, 45)
            y += rnd.randint(-45, 45)
            pts.append((x, y))
        d.line(pts, fill=(160, 120, 75), width=5)
    # dark edges (vignette)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([60, 60, W - 60, H - 60], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGB", (W, H), (110, 70, 30))
    return Image.composite(img, dark, mask)


def slug(text):
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


def landmark_photo(quiz):
    """Your own picture in images/ wins; otherwise the main Wikipedia photo of the landmark."""
    for name in (f"quiz_{quiz['number']}", slug(quiz.get("landmark", ""))):
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            path = os.path.join("images", name + ext)
            if os.path.exists(path):
                return Image.open(path).convert("RGB"), ""
    if not quiz.get("landmark"):
        return None, ""
    ua = {"User-Agent": "MonkeyQuizBot/1.0 (https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "") + ")"}
    rnd = random.Random(f"{quiz['number']}-{quiz['landmark']}")
    # 1) a real photograph (often with real people) from Wikimedia Commons
    searches = [quiz["photo_search"]] if quiz.get("photo_search") else []
    searches += [f"{quiz['landmark']} people", quiz["landmark"]]
    for text in searches:
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ua, timeout=30, params={
                "action": "query", "generator": "search", "gsrsearch": f"{text} filetype:bitmap", "gsrnamespace": 6,
                "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600,
                "format": "json"})
            pages = r.json().get("query", {}).get("pages", {}).values()
            good = []
            for pg in pages:
                ii = (pg.get("imageinfo") or [{}])[0]
                if ii.get("mime") == "image/jpeg" and ii.get("width", 0) >= 1200 and ii.get("height", 0) >= 800:
                    artist = ii.get("extmetadata", {}).get("Artist", {}).get("value", "")
                    artist = "".join(ch for ch in __import__("re").sub("<[^>]+>", "", artist) if ch.isprintable())[:40]
                    good.append((ii["thumburl"], artist))
            if good:
                url, artist = rnd.choice(good)
                img = Image.open(io.BytesIO(requests.get(url, headers=ua, timeout=60).content)).convert("RGB")
                return img, f"Photo: {artist or 'Wikimedia Commons'} / Wikimedia Commons"
        except Exception as e:
            print("Commons search failed:", e)
    # 2) the main Wikipedia photo of the landmark
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=ua, timeout=30, params={
            "action": "query", "titles": quiz["landmark"], "prop": "pageimages", "piprop": "thumbnail",
            "pithumbsize": 1600, "redirects": 1, "format": "json"})
        page = next(iter(r.json()["query"]["pages"].values()))
        img = Image.open(io.BytesIO(requests.get(page["thumbnail"]["source"], headers=ua, timeout=60).content))
        return img.convert("RGB"), "Photo: Wikipedia / Wikimedia Commons"
    except Exception as e:
        print("No landmark photo, using parchment:", e)
        return None, ""


def background(quiz):
    photo, credit = landmark_photo(quiz)
    if photo is None:
        return parchment(quiz["number"]), ""
    img = ImageOps.fit(photo, (W, H), Image.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(0.8)
    shade = Image.new("RGB", (W, H), (30, 18, 8))
    mask = Image.linear_gradient("L").resize((W, H)).point(lambda p: 150 - p // 3)
    return Image.composite(shade, img, mask), credit


def outlined(d, xy, text, f, fill, outline=(60, 30, 10), width=6, anchor="mm"):
    d.text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=width, stroke_fill=outline)


def wrap(d, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def scroll(d, box, text, size=62):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, 30, fill=(245, 230, 195), outline=(120, 80, 40), width=6)
    for yy in (y0, y1):
        d.rounded_rectangle([x0 - 30, yy - 28, x1 + 30, yy + 28], 28, fill=(214, 185, 130), outline=(120, 80, 40), width=6)
    f = font(size)
    lines = wrap(d, text, f, x1 - x0 - 80)
    while len(lines) * (size + 14) > (y1 - y0 - 70) and size > 36:
        size -= 4
        f = font(size)
        lines = wrap(d, text, f, x1 - x0 - 80)
    total = len(lines) * (size + 14)
    y = (y0 + y1) / 2 - total / 2 + size / 2
    for line in lines:
        d.text(((x0 + x1) / 2, y), line, font=f, fill=(60, 35, 15), anchor="mm")
        y += size + 14


MONKEY_FILE = next((p for p in ("images/monkey.png", "images/monkey.webp", "images/monkey.jpg") if os.path.exists(p)), None)


def monkey(d, cx, cy):
    """Your own monkey (images/monkey.png) if uploaded, otherwise a simple drawn monkey."""
    if MONKEY_FILE:
        m = Image.open(MONKEY_FILE).convert("RGBA")
        m.thumbnail((560, 600))
        d._image.paste(m, (int(cx - m.width / 2), H - m.height), m)
        return
    fur, skin, dark = (120, 72, 38), (232, 186, 136), (40, 25, 15)
    d.ellipse([cx - 210, cy + 120, cx + 210, cy + 460], fill=fur)  # body
    d.ellipse([cx - 120, cy + 170, cx + 120, cy + 420], fill=skin)  # belly
    for sx in (-1, 1):  # ears
        ex = cx + sx * 165
        d.ellipse([ex - 70, cy - 70, ex + 70, cy + 70], fill=fur)
        d.ellipse([ex - 40, cy - 40, ex + 40, cy + 40], fill=skin)
    d.ellipse([cx - 160, cy - 165, cx + 160, cy + 165], fill=fur)  # head
    d.ellipse([cx - 120, cy - 60, cx + 120, cy + 150], fill=skin)  # face
    d.ellipse([cx - 130, cy - 120, cx + 0, cy + 20], fill=skin)
    d.ellipse([cx + 0, cy - 120, cx + 130, cy + 20], fill=skin)
    for sx in (-1, 1):  # eyes
        ex = cx + sx * 55
        d.ellipse([ex - 32, cy - 75, ex + 32, cy - 5], fill="white", outline=dark, width=3)
        d.ellipse([ex - 14, cy - 52, ex + 14, cy - 20], fill=dark)
        d.ellipse([ex - 6, cy - 48, ex + 2, cy - 40], fill="white")
    d.ellipse([cx - 22, cy + 30, cx - 8, cy + 44], fill=dark)  # nose
    d.ellipse([cx + 8, cy + 30, cx + 22, cy + 44], fill=dark)
    d.chord([cx - 70, cy + 40, cx + 70, cy + 130], 0, 180, fill=(150, 40, 40), outline=dark, width=4)  # smile
    d.chord([cx - 170, cy - 220, cx + 170, cy - 20], 180, 360, fill=(200, 40, 40), outline=dark, width=4)  # cap
    d.rounded_rectangle([cx - 20, cy - 130, cx + 250, cy - 95], 18, fill=(170, 30, 30), outline=dark, width=4)  # brim
    d.ellipse([cx - 16, cy - 235, cx + 16, cy - 205], fill=(240, 200, 60))
    # microphone in hand
    d.line([(cx + 210, cy + 230), (cx + 150, cy + 90)], fill=(70, 70, 70), width=22)
    d.ellipse([cx + 112, cy + 40, cx + 182, cy + 110], fill=(30, 30, 30), outline=(110, 110, 110), width=5)
    d.ellipse([cx + 175, cy + 200, cx + 245, cy + 270], fill=fur)


def frame(bg, quiz, options, answer_idx, mode, count=None):
    img = bg.copy()
    d = ImageDraw.Draw(img)
    outlined(d, (W / 2, 140), f"QUIZ {quiz['number']}", font(150, True), (245, 196, 50), width=8)
    outlined(d, (W / 2, 275), f"{quiz['country']} Week", font(58, True), (255, 240, 210), width=4)
    if mode == "intro":
        outlined(d, (W / 2, 1020), "Can you answer", font(80, True), (255, 255, 255), width=6)
        outlined(d, (W / 2, 1120), "this one?", font(80, True), (255, 255, 255), width=6)
        monkey(d, 300, 1650)
        return img
    if mode == "answer":
        scroll(d, (110, 380, 970, 760), f"Answer: {LETTERS[answer_idx]}. {quiz['fact']}", 54)
    else:
        scroll(d, (110, 380, 970, 760), quiz["question"])
    y = 830
    for i, opt in enumerate(options):
        fill, edge, txt = (250, 238, 210), (120, 80, 40), (60, 35, 15)
        if mode == "answer":
            if i == answer_idx:
                fill, edge, txt = (70, 170, 70), (20, 90, 20), (255, 255, 255)
            else:
                fill, txt = (215, 200, 170), (140, 120, 95)
        d.rounded_rectangle([110, y, 970, y + 125], 35, fill=fill, outline=edge, width=6)
        d.ellipse([130, y + 15, 225, y + 110], fill=(245, 196, 50), outline=edge, width=5)
        d.text((177, y + 63), LETTERS[i], font=font(56), fill=(60, 35, 15), anchor="mm")
        f = font(52)
        while d.textlength(opt, font=f) > 700 and f.size > 30:
            f = font(f.size - 4)
        d.text((250, y + 63), opt, font=f, fill=txt, anchor="lm")
        y += 150
    monkey(d, 300, 1650)
    if count is not None:
        d.ellipse([700, 1480, 960, 1740], fill=(245, 196, 50), outline=(60, 30, 10), width=10)
        d.text((830, 1610), str(count), font=font(150), fill=(60, 30, 10), anchor="mm")
    elif mode == "question":
        outlined(d, (830, 1610), "?", font(220, True), (245, 196, 50))
    outlined(d, (W / 2, 1860), "Comment your answer!" if mode != "answer" else "Follow for a new quiz every day!",
             font(50), (255, 240, 210), width=4)
    return img


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def speak(text, path, fallback_seconds):
    try:
        from gtts import gTTS
        gTTS(text, lang="en").save(path)
        return
    except Exception as e:  # no voice available: use silence instead
        print("Voice failed, using silence:", e)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(fallback_seconds), path])


def make_video(quiz, workdir, video_path, thumb_path):
    rnd = random.Random(quiz["number"])
    order = list(range(4))
    rnd.shuffle(order)
    options = [quiz["options"][i] for i in order]
    answer_idx = order.index(0)  # the first option in quizzes.json is always the right one
    bg, credit = background(quiz)
    if credit:
        ImageDraw.Draw(bg).text((W - 20, H - 12), credit, font=font(22), fill=(255, 255, 255), anchor="rd",
                                stroke_width=2, stroke_fill=(0, 0, 0))

    frames = [("i.png", frame(bg, quiz, options, answer_idx, "intro")),
              ("q.png", frame(bg, quiz, options, answer_idx, "question"))]
    for c in range(COUNTDOWN, 0, -1):
        frames.append((f"c{c}.png", frame(bg, quiz, options, answer_idx, "count", c)))
    frames.append(("a.png", frame(bg, quiz, options, answer_idx, "answer")))
    for name, im in frames:
        im.save(os.path.join(workdir, name))
    frames[1][1].convert("RGB").save(thumb_path, quality=92)

    q_audio, a_audio = os.path.join(workdir, "q.mp3"), os.path.join(workdir, "a.mp3")
    opts = ". ".join(f"{LETTERS[i]}: {o}" for i, o in enumerate(options))
    speak(f"Quiz {quiz['number']}! {quiz['question']} {opts}. You have five seconds!", q_audio, 8)
    speak(f"The answer is {LETTERS[answer_idx]}: {options[answer_idx]}! {quiz['fact']}", a_audio, 5)
    q_len = duration(q_audio) + 0.5
    a_len = max(duration(a_audio) + 1.5, 4.0, MIN_LEN - (INTRO + q_len + COUNTDOWN))

    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        f.write(f"file 'i.png'\nduration {INTRO}\nfile 'q.png'\nduration {q_len:.2f}\n")
        for c in range(COUNTDOWN, 0, -1):
            f.write(f"file 'c{c}.png'\nduration 1\n")
        f.write(f"file 'a.png'\nduration {a_len:.2f}\nfile 'a.png'\n")
    total = min(INTRO + q_len + COUNTDOWN + a_len, MAX_LEN)
    d1 = int(INTRO * 1000)
    delay = int((INTRO + q_len + COUNTDOWN) * 1000)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", q_audio, "-i", a_audio,
         "-filter_complex", f"[1:a]adelay=delays={d1}:all=1[a1];[2:a]adelay=delays={delay}:all=1[a2];[a1][a2]amix=inputs=2:duration=longest:normalize=0,apad[aout]",
         "-map", "0:v", "-map", "[aout]", "-t", f"{total:.2f}", "-vf", "fps=30,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
         "-movflags", "+faststart", video_path])


def main():
    quizzes = json.load(open("quizzes.json"))
    state = json.load(open("state.json"))
    config = json.load(open("config.json"))
    os.makedirs(OUT, exist_ok=True)

    # one country per week, in the order they appear in quizzes.json
    countries = list(dict.fromkeys(q["country"] for q in quizzes))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    country = state.get("country")
    started = datetime.date.fromisoformat(state["week_started"]) if state.get("week_started") else None
    if country not in countries:
        country, started = countries[0], today
    elif (today - started).days >= 7:
        country, started = countries[(countries.index(country) + 1) % len(countries)], today
    pool = [q for q in quizzes if q["country"] == country]
    used = dict(state.get("used", {}))
    number = int(state.get("next_number", 13))

    made = []
    for _ in range(int(config.get("videos_per_day", 2))):
        quiz = dict(pool[used.get(country, 0) % len(pool)])
        used[country] = used.get(country, 0) + 1
        quiz["number"] = number
        number += 1
        workdir = os.path.join(OUT, f"work{quiz['number']}")
        os.makedirs(workdir, exist_ok=True)
        video = os.path.join(OUT, f"quiz_{quiz['number']}.mp4")
        thumb = os.path.join(OUT, f"quiz_{quiz['number']}_thumbnail.jpg")
        print("Making", video, "-", country, "-", quiz.get("landmark"))
        make_video(quiz, workdir, video, thumb)
        subprocess.run(["rm", "-rf", workdir])
        made.append({"number": quiz["number"], "country": country, "question": quiz["question"],
                     "video": video, "thumbnail": thumb})
        if used[country] == len(pool):
            print(f"::warning::All {country} quizzes have been used. Add more to quizzes.json or they will repeat.")
    new_state = {"next_number": number, "country": country, "week_started": started.isoformat(), "used": used}
    json.dump({"videos": made, "state": new_state}, open(os.path.join(OUT, "manifest.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
