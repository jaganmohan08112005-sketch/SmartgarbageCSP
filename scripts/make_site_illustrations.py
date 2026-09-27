#!/usr/bin/env python3
"""Generate clean flat site illustrations for SmartGarbage (app/static/img/).

Replaces the blurred / unsuitable stock photos with sharp, on-brand vector-style
illustrations drawn with PIL (no licence risk, matches og-image brand palette).
Run from anywhere:  python scripts/make_site_illustrations.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "app", "static", "img")
os.makedirs(OUT, exist_ok=True)

# Brand palette (sampled from og-image.png)
DEEP = (18, 70, 48)       # #124630 deep green
MID = (27, 95, 67)        # #1B5F43 brand green
SAFFRON = (255, 153, 51)  # #FF9933
AMBER = (251, 191, 36)    # #FBBF24
CREAM = (247, 245, 238)
WHITE = (255, 255, 255)
INK = (20, 40, 32)

BLUE = (52, 120, 190)     # dry bin
GREEN = (56, 158, 79)     # wet bin
RED = (200, 60, 50)       # reject bin


def font(size, bold=True):
    name = "arialbd.ttf" if bold else "arial.ttf"
    for cand in (os.path.join("C:", os.sep, "Windows", "Fonts", name),):
        if os.path.exists(cand):
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def vgrad(w, h, top, bottom):
    im = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        im.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im.resize((w, h))


def rrect(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def bin_icon(d, cx, base_y, w, h, color, lid=True):
    """Flat wheelie bin facing viewer."""
    body = (cx - w // 2, base_y - h, cx + w // 2, base_y)
    rrect(d, body, 14, color)
    if lid:
        rrect(d, (cx - w // 2 - 10, base_y - h - 18, cx + w // 2 + 10, base_y - h + 6), 10,
              tuple(min(255, c + 25) for c in color))
    # handle slot
    d.rounded_rectangle((cx - 26, base_y - h - 8, cx + 26, base_y + 2), 6, fill=tuple(max(0, c - 60) for c in color))
    # wheels
    for sx in (-1, 1):
        d.ellipse((cx + sx * (w // 2 - 16) - 12, base_y - 12, cx + sx * (w // 2 - 16) + 12, base_y + 12),
                  fill=(40, 44, 42))


def recycle_arrows(d, cx, cy, r, color=WHITE):
    """Simplified triangle recycle mark."""
    pts = [(cx, cy - r), (cx + r, cy + r * 0.75), (cx - r, cy + r * 0.75)]
    d.polygon(pts, outline=color, width=max(4, r // 5))


def leaf(d, cx, cy, s, color=WHITE):
    d.ellipse((cx - s, cy - s * 0.6, cx + s, cy + s * 0.6), fill=color)
    d.line((cx - s, cy + s * 0.6, cx + s * 0.9, cy - s * 0.55), fill=MID, width=max(3, s // 6))


def make_hero():
    """1600x900 - 4-bin source segregation system (homepage hero)."""
    W, H = 1600, 900
    im = vgrad(W, H, MID, DEEP)
    d = ImageDraw.Draw(im)
    # subtle dot texture
    for yy in range(40, H, 56):
        for xx in range(40 + (yy // 56 % 2) * 28, W, 56):
            d.ellipse((xx - 2, yy - 2, xx + 2, yy + 2), fill=(255, 255, 255, 8) and (35, 84, 62))
    # left text block
    d.text((90, 200), "SMARTGARBAGE", font=font(44), fill=AMBER)
    d.text((90, 270), "Source Segregation", font=font(84), fill=WHITE)
    d.text((90, 380), "made simple", font=font(84), fill=WHITE)
    d.text((90, 520), "Four streams at home - cleaner loads,", font=font(38, False), fill=CREAM)
    d.text((90, 575), "better recycling, greener wards.", font=font(38, False), fill=CREAM)
    d.rectangle((90, 480, 300, 488), fill=SAFFRON)
    # right: 4 bins
    labels = [("DRY", BLUE), ("WET", GREEN), ("RECYCLE", AMBER), ("REJECT", RED)]
    base_y, bh, bw = 780, 300, 150
    xs = [950, 1130, 1310, 1480]
    for (lab, col), cx in zip(labels, xs):
        bin_icon(d, cx, base_y, bw, bh, col)
        f = font(26)
        tw = d.textlength(lab, font=f)
        d.text((cx - tw / 2, base_y + 26), lab, font=f, fill=WHITE)
    # icons on bins
    recycle_arrows(d, xs[2], base_y - 150, 34)
    leaf(d, xs[1], base_y - 150, 30)
    # drop + cross glyphs
    d.ellipse((xs[0] - 24, base_y - 176, xs[0] + 24, base_y - 128), fill=WHITE)
    d.polygon([(xs[3] - 26, base_y - 176), (xs[3] + 26, base_y - 124)],
              fill=WHITE)
    d.polygon([(xs[3] + 26, base_y - 176), (xs[3] - 26, base_y - 124)], fill=WHITE)
    # ground line
    d.rectangle((880, base_y + 64, 1600, base_y + 74), fill=(14, 56, 40))
    p = os.path.join(OUT, "hero-recycle.jpg")
    im.save(p, "JPEG", quality=88)
    print("wrote", p)


def make_workers():
    """1000x667 - five-ward collection round: truck + bins."""
    W, H = 1000, 667
    im = vgrad(W, H, (222, 238, 230), CREAM)
    d = ImageDraw.Draw(im)
    # sun + skyline
    d.ellipse((790, 60, 900, 170), fill=AMBER)
    for i, (bx, bh) in enumerate([(60, 120), (170, 90), (700, 110), (830, 80)]):
        d.rectangle((bx, 330 - bh, bx + 110, 330), fill=(206, 226, 214))
    # road
    d.rectangle((0, 430, W, 560), fill=(108, 114, 112))
    for x in range(20, W, 90):
        d.rectangle((x, 490, x + 46, 502), fill=CREAM)
    # truck: cab + body
    body_y = 330
    rrect(d, (250, body_y, 640, 450), 16, MID)
    rrect(d, (640, body_y + 40, 800, 450), 14, SAFFRON)
    d.rounded_rectangle((668, body_y + 60, 762, body_y + 95), 10, fill=(210, 232, 240))
    # hopper stripes
    for x in range(280, 620, 44):
        d.rectangle((x, body_y + 30, x + 22, 420), fill=(23, 78, 56))
    # wheels
    for cx in (330, 570, 730):
        d.ellipse((cx - 38, 430, cx + 38, 506), fill=(35, 39, 37))
        d.ellipse((cx - 16, 448, cx + 16, 488), fill=(160, 166, 162))
    # kerb bins
    for cx, col in ((120, GREEN), (200, BLUE), (880, AMBER)):
        bin_icon(d, cx, 470, 92, 150, col)
    # ward chips
    f = font(30)
    for i in range(5):
        x0 = 90 + i * 168
        rrect(d, (x0, 596, x0 + 128, 640), 22, MID if i % 2 == 0 else SAFFRON)
        t = f"WARD {i + 1}"
        d.text((x0 + (128 - d.textlength(t, font=f)) / 2, 602), t, font=f, fill=WHITE)
    d.text((60, 24), "COLLECTION ROUND - FIVE WARDS", font=font(40), fill=INK)
    p = os.path.join(OUT, "about-workers.jpg")
    im.save(p, "JPEG", quality=88)
    print("wrote", p)


def make_sorting():
    """1200x800 - at-home segregation earns Green Points."""
    W, H = 1200, 800
    im = vgrad(W, H, CREAM, (233, 240, 232))
    d = ImageDraw.Draw(im)
    d.text((70, 50), "SEGREGATE AT HOME", font=font(46), fill=INK)
    d.text((70, 112), "earn Green Points on every handover", font=font(32, False), fill=(90, 110, 100))
    # room floor line
    d.rectangle((0, 640, W, H), fill=(226, 231, 222))
    # two bins: wrong (grey, crossed) vs right (green, tick)
    bin_icon(d, 330, 640, 190, 300, (150, 156, 152))
    bin_icon(d, 760, 640, 190, 300, GREEN)
    recycle_arrows(d, 760, 500, 36)
    # cross over grey bin
    d.line((260, 380, 400, 520), fill=RED, width=16)
    d.line((400, 380, 260, 520), fill=RED, width=16)
    # items flying into green bin: bottle + paper + can
    d.rounded_rectangle((560, 250, 600, 330), 14, outline=BLUE, width=8)
    d.rectangle((520, 360, 620, 410), outline=(160, 120, 60), width=8)
    d.rounded_rectangle((640, 300, 690, 370), 12, outline=(120, 126, 122), width=8)
    for x, y in ((580, 340), (570, 420), (665, 385)):
        d.polygon([(x - 14, y - 26), (x + 2, y + 6), (x - 22, y + 6)], fill=SAFFRON)
    # Green Points badge
    bx, by = 830, 150
    d.ellipse((bx, by, bx + 300, by + 150), fill=DEEP)
    d.ellipse((bx + 8, by + 8, bx + 292, by + 142), outline=AMBER, width=6)
    d.text((bx + 48, by + 26), "GREEN", font=font(44), fill=AMBER)
    d.text((bx + 44, by + 86), "+120 POINTS", font=font(34), fill=WHITE)
    leaf(d, bx + 252, by + 40, 22)
    p = os.path.join(OUT, "about-sorting.jpg")
    im.save(p, "JPEG", quality=88)
    print("wrote", p)


def make_cards():
    """1280x720 title & outro cards for the demo video."""
    vd = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "report", "video")
    os.makedirs(vd, exist_ok=True)
    # title
    im = vgrad(1280, 720, MID, DEEP)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 14, 720), fill=SAFFRON)
    d.rectangle((14, 0, 26, 720), fill=WHITE)
    d.rectangle((26, 0, 40, 720), fill=GREEN)
    d.text((100, 200), "SmartGarbage Chintalavalasa", font=font(64), fill=WHITE)
    d.text((100, 300), "Official Municipal Waste Portal - Website Walkthrough",
           font=font(34, False), fill=CREAM)
    d.text((100, 420), "Collection Schedules  -  Missed Pickup Reports  -  Green Points",
           font=font(28, False), fill=AMBER)
    d.text((100, 560), "smartgarbage.onrender.com", font=font(30), fill=WHITE)
    p = os.path.join(vd, "card_title.png")
    im.save(p, "PNG")
    print("wrote", p)
    # outro
    im = vgrad(1280, 720, DEEP, MID)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 14, 720), fill=SAFFRON)
    d.rectangle((14, 0, 26, 720), fill=WHITE)
    d.rectangle((26, 0, 40, 720), fill=GREEN)
    d.text((100, 190), "Thank you", font=font(72), fill=WHITE)
    d.text((100, 320), "SmartGarbage Chintalavalasa - clean wards, accountable data,", font=font(30, False), fill=CREAM)
    d.text((100, 370), "zero cost to the panchayat.", font=font(30, False), fill=CREAM)
    d.text((100, 480), "Team Batch 2  -  CSE (Data Science), MVGR (A)", font=font(26, False), fill=AMBER)
    d.text((100, 560), "smartgarbage.onrender.com   -   Helpline 1800 119 9111", font=font(28), fill=WHITE)
    p = os.path.join(vd, "card_outro.png")
    im.save(p, "PNG")
    print("wrote", p)


if __name__ == "__main__":
    make_hero()
    make_workers()
    make_sorting()
    make_cards()
