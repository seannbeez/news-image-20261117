"""Draw the World News Brief v2 — "Visual-First Executive Briefing".

3:2 broadsheet, 1024x683, deterministic PIL rendering (no image model,
so every letter is exact): warm ivory page, navy + crimson accents, a
serif masthead naming Tuesday 17 November 2026, a simplified editorial
world map on the left with three numbered flashpoint pins, and six
data cards on the right covering all seven verified stories of the
day. Output: entry.png, 1024x683, well under 1 MiB.
"""

import math

from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 683
IVORY = (247, 244, 235)
INK = (19, 41, 61)          # deep navy, also the main text ink
NAVY = (19, 41, 61)
CRIMSON = (193, 41, 46)
CARD_BG = (255, 253, 247)
SUBINK = (64, 74, 84)
LAND = (176, 196, 209)      # pale steel blue landmasses
LAND_LINE = (19, 41, 61)

SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_c(draw, cx, y, text, fnt, fill=INK):
    w = draw.textlength(text, font=fnt)
    draw.text((cx - w / 2, y), text, font=fnt, fill=fill)


# ---------------------------------------------------------------- map
# Simplified continents as flat polygons, in fractions of the map box.
CONTINENTS = [
    # North America
    [(0.03, 0.16), (0.06, 0.08), (0.14, 0.05), (0.24, 0.07), (0.30, 0.12),
     (0.28, 0.18), (0.24, 0.24), (0.20, 0.30), (0.22, 0.38), (0.18, 0.45),
     (0.15, 0.36), (0.10, 0.34), (0.05, 0.28), (0.02, 0.22)],
    # Greenland
    [(0.29, 0.02), (0.34, 0.02), (0.34, 0.08), (0.29, 0.08)],
    # South America
    [(0.20, 0.48), (0.28, 0.46), (0.33, 0.52), (0.32, 0.66), (0.27, 0.82),
     (0.23, 0.78), (0.20, 0.62)],
    # Europe
    [(0.47, 0.10), (0.53, 0.08), (0.58, 0.12), (0.57, 0.20), (0.52, 0.24),
     (0.47, 0.20), (0.45, 0.14)],
    # Africa
    [(0.46, 0.32), (0.55, 0.30), (0.61, 0.36), (0.60, 0.50), (0.55, 0.62),
     (0.50, 0.60), (0.46, 0.46)],
    # Asia
    [(0.58, 0.08), (0.70, 0.05), (0.85, 0.08), (0.97, 0.14), (0.95, 0.26),
     (0.88, 0.34), (0.80, 0.30), (0.74, 0.38), (0.68, 0.30), (0.60, 0.22),
     (0.57, 0.14)],
    # SE Asia peninsula
    [(0.78, 0.34), (0.82, 0.42), (0.80, 0.48), (0.76, 0.42)],
    # Philippines
    [(0.80, 0.44), (0.83, 0.45), (0.83, 0.50), (0.81, 0.51), (0.79, 0.47)],
    # Japan
    [(0.93, 0.18), (0.95, 0.19), (0.94, 0.25), (0.92, 0.23)],
    # Britain
    [(0.45, 0.11), (0.47, 0.11), (0.47, 0.16), (0.45, 0.16)],
    # Australia
    [(0.80, 0.62), (0.90, 0.60), (0.95, 0.66), (0.92, 0.74), (0.84, 0.74),
     (0.79, 0.68)],
]

# (number, place, descriptor, map-fraction x, y)
PINS = [
    (2, "KERCH STRAIT", "Bridge hit in major strike", 0.575, 0.17),
    (3, "STRAIT OF HORMUZ", "Qeshm blast, tankers hit", 0.665, 0.335),
    (1, "MANILA", "ASEAN Summit; Trump arrives", 0.815, 0.475),
]

# Label chips, in map-relative pixels (map box 420 x 430), drawn after
# the leader lines so no line crosses a chip's text.
CHIPS = {
    2: (8, 8),
    3: (110, 200),
    1: (200, 258),
}


def draw_map(d, x0, y0, w, h):
    # Ocean panel.
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=(233, 238, 240),
                outline=NAVY, width=2)
    for poly in CONTINENTS:
        pts = [(x0 + fx * w, y0 + fy * h) for fx, fy in poly]
        d.polygon(pts, fill=LAND, outline=LAND_LINE)
    # Leader lines first, then pins, then chips on top.
    pins_px = {}
    for num, _place, _desc, fx, fy in PINS:
        px, py = x0 + fx * w, y0 + fy * h
        pins_px[num] = (px, py)
        cx, cy = CHIPS[num]
        d.line([x0 + cx + 100, y0 + cy + 46, px, py], fill=NAVY, width=2)
    for num, place, desc, _fx, _fy in PINS:
        px, py = pins_px[num]
        r = 13
        d.ellipse([px - r, py - r, px + r, py + r], fill=CRIMSON,
                  outline=(255, 255, 255), width=2)
        num_font = font(SANS_B, 15)
        tw = d.textlength(str(num), font=num_font)
        d.text((px - tw / 2, py - 10), str(num), font=num_font,
               fill=(255, 255, 255))
    for num, place, desc, _fx, _fy in PINS:
        cx, cy = CHIPS[num]
        bx, by = x0 + cx, y0 + cy
        d.rounded_rectangle([bx, by, bx + 200, by + 46], radius=6,
                            fill=(255, 253, 247), outline=NAVY, width=2)
        d.text((bx + 10, by + 5), f"{num}  {place}", font=font(SANS_B, 15),
               fill=NAVY)
        d.text((bx + 10, by + 25), desc, font=font(SANS, 12), fill=SUBINK)


# ---------------------------------------------------------------- cards
# (badge, badge colour, headline, sub-or-None) — Fura's exact wording.
CARDS = [
    ("ASIA-PACIFIC", NAVY, "49th ASEAN Summit Opens in Manila", None),
    ("CONFLICT", CRIMSON, "Kerch Bridge Hit in Major Strike", None),
    ("MIDDLE EAST", (176, 122, 30), "Hormuz Tanker Attacks Escalate Tensions", None),
    ("TRADE — $280M", (31, 122, 77), "China & Canada Cut Tariffs Pre-APEC", None),
    ("TECH", (96, 52, 140), "US Tightens AI Chip Curbs",
     "Licences for 5 nations; Megaspeed probed"),
    ("TECH & ENERGY", (15, 110, 110), "UK Ends Palantir NHS Deal; Japan Oil Plan", None),
]


def draw_card(d, x, y, w, h, badge, color, headline, sub=None):
    d.rectangle([x, y, x + w, y + h], fill=CARD_BG, outline=NAVY, width=2)
    d.rectangle([x, y, x + 6, y + h], fill=color)
    badge_font = font(SANS_B, 14)
    bw = d.textlength(badge, font=badge_font) + 20
    head_font = font(SERIF_B, 23)
    lines = wrap(d, headline, head_font, w - 28)
    block_h = 22 + 6 + len(lines) * 26 + (24 if sub else 0)
    ty = y + (h - block_h) // 2
    tx = x + 20
    d.rounded_rectangle([tx, ty, tx + bw, ty + 22], radius=11, fill=color)
    d.text((tx + 10, ty + 3), badge, font=badge_font, fill=(255, 255, 255))
    ly = ty + 28
    for line in lines:
        d.text((tx, ly), line, font=head_font, fill=INK)
        ly += 26
    if sub:
        d.text((tx, ly + 2), sub, font=font(SANS, 17), fill=SUBINK)


def main():
    img = Image.new("RGB", (W, H), IVORY)
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, W - 7, H - 7], outline=NAVY, width=3)

    text_c(d, W // 2, 16, "THE WORLD TODAY — 17 NOVEMBER 2026",
           font(SERIF_B, 40))
    text_c(d, W // 2, 62, "GLOBAL EXECUTIVE BRIEFING", font(SANS_B, 19),
           fill=CRIMSON)
    d.line([24, 92, W - 24, 92], fill=NAVY, width=2)

    # Hero map, left ~45%.
    d.text((16, 102), "WORLD MAP — THREE FLASHPOINTS",
           font=font(SANS_B, 15), fill=NAVY)
    draw_map(d, 16, 126, 420, 524)
    d.text((26, 628), "Pins mark the three flashpoints; all seven stories at right.",
           font=font(SERIF, 13), fill=SUBINK)

    # Data cards, right ~55%.
    cx, cy, cw, chh, gap = 452, 96, 556, 89, 6
    for i, (badge, color, head, sub) in enumerate(CARDS):
        draw_card(d, cx, cy + i * (chh + gap), cw, chh, badge, color, head, sub)

    img.save("entry.png", optimize=True)
    print("wrote entry.png", img.size)


if __name__ == "__main__":
    main()
