"""Draw the World News Brief broadsheet for Tuesday 17 November 2026.

Deterministic PIL rendering (no image model, so every letter is exact):
a cream newsprint page, a serif masthead naming the day, and six bordered
grid cards, one per verified story, each with a coloured tag, a short
headline, one line of subtext and a small flat icon drawn from shapes.
Output: entry.png, 1024x1024, well under the 1 MiB limit.
"""

from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 1024
CREAM = (247, 245, 240)
INK = (20, 20, 20)
RULE = (20, 20, 20)
SUBINK = (58, 58, 58)
CARD_BG = (255, 253, 248)

SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, max_w):
    """Greedy word wrap measured in real pixels."""
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


# ---------------------------------------------------------------- icons
def icon_summit(d, x, y, s):
    # Three flags over a summit hall.
    d.rectangle([x, y + s * 0.62, x + s, y + s * 0.95], fill=(38, 70, 120))
    d.polygon([(x, y + s * 0.62), (x + s * 0.18, y + s * 0.42),
               (x + s * 0.82, y + s * 0.42), (x + s, y + s * 0.62)],
              fill=(52, 96, 158))
    for i, col in enumerate([(178, 34, 34), (34, 120, 70), (212, 160, 32)]):
        px = x + s * (0.22 + 0.28 * i)
        d.line([px, y + s * 0.05, px, y + s * 0.45], fill=INK, width=4)
        d.polygon([(px, y + s * 0.05), (px + s * 0.20, y + s * 0.12),
                   (px, y + s * 0.19)], fill=col)


def icon_bridge(d, x, y, s):
    # A bridge deck with its middle span broken and fallen, over water.
    d.line([x, y + s * 0.30, x + s * 0.36, y + s * 0.30], fill=INK, width=8)
    d.line([x + s * 0.64, y + s * 0.30, x + s, y + s * 0.30], fill=INK, width=8)
    d.line([x + s * 0.38, y + s * 0.30, x + s * 0.56, y + s * 0.52],
           fill=(178, 34, 34), width=8)
    d.line([x + s * 0.16, y + s * 0.30, x + s * 0.16, y + s * 0.56], fill=INK, width=6)
    d.line([x + s * 0.84, y + s * 0.30, x + s * 0.84, y + s * 0.56], fill=INK, width=6)
    for i, wy in enumerate([0.68, 0.80, 0.92]):
        d.arc([x + s * 0.08 + i * s * 0.05, y + s * wy, x + s * 0.42 + i * s * 0.05,
               y + s * (wy + 0.08)], 0, 180, fill=(52, 96, 158), width=5)


def icon_tanker(d, x, y, s):
    # A tanker under an orange blast burst.
    cx, cy = x + s * 0.5, y + s * 0.22
    for k in range(8):
        ang = k * 3.14159 / 4
        d.line([cx + 0.10 * s * _cos(ang), cy + 0.10 * s * _sin(ang),
                cx + 0.30 * s * _cos(ang), cy + 0.30 * s * _sin(ang)],
               fill=(224, 122, 26), width=6)
    d.ellipse([cx - s * 0.09, cy - s * 0.09, cx + s * 0.09, cy + s * 0.09],
              fill=(224, 122, 26))
    d.polygon([(x + s * 0.06, y + s * 0.58), (x + s * 0.94, y + s * 0.58),
               (x + s * 0.84, y + s * 0.82), (x + s * 0.16, y + s * 0.82)],
              fill=(38, 70, 120))
    d.rectangle([x + s * 0.62, y + s * 0.40, x + s * 0.78, y + s * 0.58],
                fill=(178, 34, 34))
    d.line([x, y + s * 0.90, x + s, y + s * 0.90], fill=(52, 96, 158), width=5)


def _cos(a):
    import math
    return math.cos(a)


def _sin(a):
    import math
    return math.sin(a)


def icon_trade(d, x, y, s):
    # Stacked shipping containers with a downward tariff arrow.
    cols = [(178, 34, 34), (34, 120, 70), (38, 70, 120)]
    for row, col in enumerate(cols):
        yy = y + s * (0.16 + row * 0.22)
        d.rectangle([x + s * 0.06, yy, x + s * 0.62, yy + s * 0.18], fill=col)
        for k in range(1, 4):
            d.line([x + s * (0.06 + 0.14 * k), yy, x + s * (0.06 + 0.14 * k),
                    yy + s * 0.18], fill=(255, 255, 255), width=3)
    d.line([x + s * 0.82, y + s * 0.14, x + s * 0.82, y + s * 0.78],
           fill=(34, 120, 70), width=8)
    d.polygon([(x + s * 0.68, y + s * 0.66), (x + s * 0.96, y + s * 0.66),
               (x + s * 0.82, y + s * 0.86)], fill=(34, 120, 70))


def icon_tech(d, x, y, s):
    # A hospital screen whose data cable is cut.
    d.rectangle([x + s * 0.08, y + s * 0.10, x + s * 0.92, y + s * 0.72],
                outline=INK, width=5, fill=(255, 255, 255))
    d.rectangle([x + s * 0.42, y + s * 0.22, x + s * 0.58, y + s * 0.58],
                fill=(178, 34, 34))
    d.rectangle([x + s * 0.30, y + s * 0.34, x + s * 0.70, y + s * 0.46],
                fill=(178, 34, 34))
    d.line([x + s * 0.30, y + s * 0.82, x + s * 0.42, y + s * 0.82], fill=INK, width=5)
    d.line([x + s * 0.58, y + s * 0.82, x + s * 0.72, y + s * 0.94], fill=(178, 34, 34), width=5)
    d.line([x + s * 0.42, y + s * 0.72, x + s * 0.42, y + s * 0.82], fill=INK, width=5)
    d.line([x + s * 0.58, y + s * 0.72, x + s * 0.58, y + s * 0.82], fill=INK, width=5)


def icon_energy(d, x, y, s):
    # An oil barrel under a flame.
    d.polygon([(x + s * 0.50, y + s * 0.06), (x + s * 0.64, y + s * 0.26),
               (x + s * 0.36, y + s * 0.26)], fill=(224, 122, 26))
    d.rectangle([x + s * 0.22, y + s * 0.34, x + s * 0.78, y + s * 0.92],
                fill=(38, 70, 120))
    d.rectangle([x + s * 0.22, y + s * 0.46, x + s * 0.78, y + s * 0.52], fill=INK)
    d.rectangle([x + s * 0.22, y + s * 0.68, x + s * 0.78, y + s * 0.74], fill=INK)


STORIES = [
    ("GEOPOLITICS", (38, 70, 120), "Trump lands in Manila",
     "49th ASEAN Summit opens amid protests", icon_summit),
    ("CONFLICT", (178, 34, 34), "Kerch Bridge span collapses",
     "Ukraine strike halts Crimea traffic", icon_bridge),
    ("MIDDLE EAST", (146, 94, 20), "Blasts rock Qeshm Island",
     "Iran reports US strike; tankers hit in Hormuz", icon_tanker),
    ("TRADE", (34, 120, 70), "China cuts Canada tariffs",
     "$280M relief on pork and seafood", icon_trade),
    ("TECH", (96, 52, 140), "NHS Palantir deal ends 2029",
     "UK skips break clause, plans new tender", icon_tech),
    ("ENERGY", (18, 110, 120), "Japan pitches Asian oil pact",
     "Shared stockpiles eyed as Asian IEA", icon_energy),
]


def draw_card(d, x, y, w, h, tag, color, headline, sub, icon_fn):
    d.rectangle([x, y, x + w, y + h], fill=CARD_BG, outline=INK, width=3)
    d.rectangle([x, y, x + w, y + 5], fill=color)
    pad = 18
    tx = x + pad
    ty = y + 20
    tag_font = font(SANS_B, 17)
    tw = d.textlength(tag, font=tag_font) + 22
    d.rounded_rectangle([tx, ty, tx + tw, ty + 30], radius=15, fill=color)
    d.text((tx + 11, ty + 5), tag, font=tag_font, fill=(255, 255, 255))
    icon_fn(d, x + w - 152, y + 76, 132)
    text_w = w - pad * 2 - 152
    head_font = font(SERIF_B, 30)
    lines = wrap(d, headline, head_font, text_w)
    ly = ty + 46
    for line in lines:
        d.text((tx, ly), line, font=head_font, fill=INK)
        ly += 38
    sub_font = font(SANS, 20)
    for line in wrap(d, sub, sub_font, text_w):
        d.text((tx, ly + 4), line, font=sub_font, fill=SUBINK)
        ly += 27


def main():
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, W - 9, H - 9], outline=INK, width=3)
    d.rectangle([16, 16, W - 17, H - 17], outline=INK, width=1)

    text_c(d, W // 2, 34, "WORLD NEWS BRIEF", font(SERIF_B, 66))
    d.line([60, 122, W - 60, 122], fill=RULE, width=3)
    text_c(d, W // 2, 134, "TUESDAY, 17 NOVEMBER 2026", font(SANS_B, 30))
    text_c(d, W // 2, 172, "Six stories from around the world — as reported on 17 November 2026",
           font(SERIF, 20), fill=SUBINK)

    gx, gy = 24, 206
    cw, chh, gap = 480, 240, 12
    for i, (tag, color, head, sub, icon_fn) in enumerate(STORIES):
        cx = gx + (i % 2) * (cw + gap)
        cy = gy + (i // 2) * (chh + gap)
        draw_card(d, cx, cy, cw, chh, tag, color, head, sub, icon_fn)

    text_c(d, W // 2, 962, "Sources: as reported 17 Nov 2026 — Reuters, BusinessWorld, Computer Weekly and others.",
           font(SANS, 15), fill=SUBINK)
    img.save("entry.png", optimize=True)
    print("wrote entry.png", img.size)


if __name__ == "__main__":
    main()
