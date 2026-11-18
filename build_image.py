"""Draw the World News Brief v3 — portrait Swiss poster.

819x1024 (4:5) deterministic PIL rendering (no image model, no SVG
toolchain on this VM — resvg, CairoSVG and pngquant are all absent —
so the poster is drawn directly with Pillow; every letter is exact).
Swiss International Typographic Style: Arctic Paper background,
Carbon Black ink, Electric Cobalt diplomacy/trade, Signal Vermilion
conflict, Acid Lime tech/energy. Four zones: masthead, a real
Robinson-projection world map (Natural Earth coastlines from
data/coast.json, simplified from data/countries.geo.json by
tools/prep_coast.py), seven developments, footer. Output: entry.png,
819x1024, under 1 MiB.
"""

import json
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 819, 1024
PAPER = (241, 243, 237)     # Arctic Paper
INK = (32, 35, 38)          # Carbon Black
COBALT = (32, 43, 235)      # Electric Cobalt
VERMILION = (240, 82, 60)   # Signal Vermilion
LIME = (213, 240, 74)       # Acid Lime
LAND = (220, 226, 219)
OCEAN = (228, 233, 228)
GRAT = (188, 197, 194)
LAND_LINE = (140, 150, 145)
SUBINK = (70, 76, 72)
CARD_BG = (255, 255, 255)

SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B_DJ = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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


def fit_font(draw, text, path, start, max_w, minimum=40):
    size = start
    while size > minimum and draw.textlength(text, font=font(path, size)) > max_w:
        size -= 1
    return font(path, size)


# ---------------------------------------------------------------- Robinson
# Standard Robinson lookup table (Snyder), X and Y per 5 degrees of
# latitude; linearly interpolated between rows.
ROBINSON = [
    (0, 1.0000, 0.0000), (5, 0.9986, 0.0620), (10, 0.9954, 0.1240),
    (15, 0.9900, 0.1860), (20, 0.9822, 0.2480), (25, 0.9730, 0.3100),
    (30, 0.9600, 0.3720), (35, 0.9427, 0.4340), (40, 0.9216, 0.4958),
    (45, 0.8962, 0.5571), (50, 0.8679, 0.6176), (55, 0.8350, 0.6769),
    (60, 0.7986, 0.7346), (65, 0.7597, 0.7903), (70, 0.7186, 0.8435),
    (75, 0.6732, 0.8936), (80, 0.6213, 0.9394), (85, 0.5722, 0.9761),
    (90, 0.5322, 1.0000),
]

LON0, LON1 = -180.0, 180.0
LAT0, LAT1 = -60.0, 90.0  # Antarctica cropped, standard for news maps;
# the top edge is the North Pole line, so great-circle arcs that pass
# near the pole stay inside the box.


def _robinson_xy(lat_deg):
    a = abs(lat_deg)
    for i in range(len(ROBINSON) - 1):
        la, xa, ya = ROBINSON[i]
        lb, xb, yb = ROBINSON[i + 1]
        if la <= a <= lb:
            t = (a - la) / (lb - la) if lb > la else 0.0
            x = xa + t * (xb - xa)
            y = ya + t * (yb - ya)
            return x, y if lat_deg >= 0 else -y
    return ROBINSON[-1][1], ROBINSON[-1][2] if lat_deg >= 0 else -ROBINSON[-1][2]


class RobinsonMap:
    """Robinson projection fitted into a w x h box, equal scale, with a
    small inset so the North Pole line and the great-circle arcs that
    pass near it stay visibly inside the frame."""

    def __init__(self, w, h, pad=8):
        x_range = 2 * 0.8487 * math.pi
        y_top = 1.3523 * _robinson_xy(LAT1)[1]
        y_bot = 1.3523 * _robinson_xy(LAT0)[1]
        y_range = y_top - y_bot
        self.scale = min((w - 2 * pad) / x_range, (h - 2 * pad) / y_range)
        self.cx = w / 2
        self.cy = (pad + (h - 2 * pad - y_range * self.scale) / 2
                   + y_top * self.scale)

    def project(self, lon, lat):
        x_factor, y_factor = _robinson_xy(lat)
        x = self.cx + 0.8487 * x_factor * math.radians(lon) * self.scale
        y = self.cy - 1.3523 * y_factor * self.scale
        return x, y


def split_ring(ring):
    """Split a lon/lat ring at antimeridian jumps so no edge is drawn
    across the whole map. Returns a list of sub-rings."""
    parts, cur = [], []
    prev = None
    for lon, lat in ring:
        if prev is not None and abs(lon - prev) > 180.0:
            if len(cur) >= 3:
                parts.append(cur)
            cur = []
        cur.append((lon, lat))
        prev = lon
    if len(cur) >= 3:
        parts.append(cur)
    return parts


def bezier(p0, p1, p2, t):
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
    return x, y


def _vec(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
            math.sin(la))


def great_circle(a, b, n=120):
    """True great-circle route between two (lat, lon) points, sampled
    with slerp. A Bezier chord would wrongly cut across the Atlantic
    and Africa for US–Singapore; the real route goes over the Arctic."""
    va, vb = _vec(*a), _vec(*b)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(va, vb))))
    omega = math.acos(dot)
    pts = []
    for i in range(n + 1):
        t = i / n
        s = math.sin(omega)
        v = tuple((math.sin((1 - t) * omega) * x + math.sin(t * omega) * y)
                  / s for x, y in zip(va, vb))
        lat = math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))
        lon = math.degrees(math.atan2(v[1], v[0]))
        pts.append((lat, lon))
    return pts


def dashed_polyline(d, pts, fill, width, dash=10, gap=7):
    run, on = 0.0, True
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i + 1][0] - pts[i][0],
                         pts[i + 1][1] - pts[i][1])
        if on:
            d.line([pts[i], pts[i + 1]], fill=fill, width=width)
        run += seg
        if run >= (dash if on else gap):
            run = 0.0
            on = not on


def solid_curve(d, p0, p1, p2, fill, width):
    n = 120
    pts = [bezier(p0, p1, p2, i / n) for i in range(n + 1)]
    d.line(pts, fill=fill, width=width)


# ---------------------------------------------------------------- map data
# (number, chip label, latitude, longitude, kind, colour)
MARKERS = [
    (1, "MANILA", 14.60, 120.98, "pin", VERMILION),
    (2, "KERCH STRAIT", 45.35, 36.60, "pin", VERMILION),
    (3, "HORMUZ", 26.75, 56.05, "pin", VERMILION),
    (6, "LONDON", 51.51, -0.13, "badge", LIME),
    (7, "TOKYO", 35.68, 139.69, "badge", LIME),
]
# Arcs: (number, chip label, lat/lon A, lat/lon B, colour). Drawn as
# true great circles (slerp), not Bezier chords.
ARCS = [
    (4, "CHINA–CANADA", (22.55, 114.06), (45.42, -75.70), COBALT),
    (5, "US–SINGAPORE", (38.90, -77.04), (1.35, 103.82), LIME),
]

# Ocean labels: (text, x, y) in map coordinates; chips may not cover them.
OCEAN_LABELS = [
    ("ATLANTIC OCEAN", 265, 122),
    ("SOUTH ATLANTIC OCEAN", 310, 290),
    ("INDIAN OCEAN", 515, 245),
    ("SOUTHERN OCEAN", 600, 310),
]


def rects_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def overlap_area(a, b):
    if not rects_overlap(a, b):
        return 0.0
    return (min(a[2], b[2]) - max(a[0], b[0])) * (
        min(a[3], b[3]) - max(a[1], b[1])
    )


def place_chips(d, anchors, avoid, w, h, forbidden=()):
    """Greedy chip placement around anchor points. anchors: {num:
    (x, y)}; avoid: [(x, y)] points no chip may cover or crowd;
    forbidden: [rect] areas (ocean labels) no chip may overlap.
    Returns {num: (rect, leader_end)}."""
    chip_font = font(SANS_B, 12)
    placed = {}
    labels = {m[0]: m[1] for m in MARKERS}
    labels.update({a[0]: a[1] for a in ARCS})
    order = [1, 5, 4, 7, 2, 3, 6]  # crowded East Asia first
    for num in order:
        label = f"{num:02d} {labels[num]}"
        cw = d.textlength(label, font=chip_font) + 16
        ch = 22
        px, py = anchors[num]
        candidates = [
            (14, -11), (-14 - cw, -11), (14, -33), (-14 - cw, -33),
            (14, 11), (-14 - cw, 11), (-cw // 2, -36), (-cw // 2, 14),
        ]
        for gx in range(-280, 81, 20):
            for gy in range(-70, 71, 20):
                candidates.append((gx, gy))
        best = None
        for dx, dy in candidates:
            rect = (px + dx, py + dy, px + dx + cw, py + dy + ch)
            score = 0.0
            if rect[0] < 2 or rect[1] < 2 or rect[2] > w - 2 or rect[3] > h - 2:
                score += 10000
                score += 100 * (
                    max(0, 2 - rect[0]) + max(0, 2 - rect[1])
                    + max(0, rect[2] - (w - 2)) + max(0, rect[3] - (h - 2))
                )
            for other_rect, _ in placed.values():
                score += overlap_area(rect, other_rect) * 50
            for f in forbidden:
                score += overlap_area(rect, f) * 50
            for ax, ay in avoid:
                cx = min(max(ax, rect[0]), rect[2])
                cy = min(max(ay, rect[1]), rect[3])
                if math.hypot(ax - cx, ay - cy) < 18:
                    score += 5000
            score += math.hypot(dx + cw / 2, dy + ch / 2) * 0.5
            if best is None or score < best[0]:
                best = (score, rect)
        _, rect = best
        cx = min(max(px, rect[0]), rect[2])
        cy = min(max(py, rect[1]), rect[3])
        placed[num] = (rect, (cx, cy))
        print(f"chip {num:02d}: rect {tuple(round(v) for v in rect)} "
              f"score {best[0]:.0f}")
        if best[0] > 1000:
            print(f"WARNING: chip {num:02d} placement scored {best[0]:.0f}")
    return placed


def draw_map(img, x0, y0, w, h):
    d = ImageDraw.Draw(img)
    coast = json.loads((HERE / "data" / "coast.json").read_text())
    proj = RobinsonMap(w, h)
    tmp = Image.new("RGB", (w, h), OCEAN)
    t = ImageDraw.Draw(tmp)
    # Graticule every 15 degrees: meridians as curves, parallels as
    # straight lines (Robinson parallels are horizontal).
    for lon in range(-165, 181, 15):
        pts = [proj.project(lon, lat) for lat in range(-60, 91, 5)]
        t.line(pts, fill=GRAT, width=1)
    for lat in range(-60, 91, 15):
        x1, gy = proj.project(-180, lat)
        x2, _ = proj.project(180, lat)
        t.line([x1, gy, x2, gy], fill=GRAT, width=1)
    # Real coastlines, split at the antimeridian.
    for poly in coast["polys"]:
        for part in split_ring(poly):
            pts = [proj.project(lon, lat) for lon, lat in part]
            t.polygon(pts, fill=LAND, outline=LAND_LINE)
    # Ocean labels (legit cartographic detail), kept clear of chips.
    label_font = font("/usr/share/fonts/truetype/liberation/"
                      "LiberationSans-Italic.ttf", 12)
    label_rects = []
    for text, lx, ly in OCEAN_LABELS:
        lw = t.textlength(text, font=label_font)
        label_rects.append((lx, ly, lx + lw, ly + 15))
        t.text((lx, ly), text, font=label_font, fill=(120, 130, 125))
    # Arcs (drawn under the pins): true great circles.
    anchors = {}
    avoid = []
    arc_mids = {}
    for num, _label, a, b, color in ARCS:
        route = [proj.project(lon, lat)
                 for lat, lon in great_circle(a, b)]
        ax, ay = route[0]
        bx, by = route[-1]
        mid = route[len(route) // 2]
        arc_mids[num] = mid
        anchors[num] = mid
        avoid += [(ax, ay), (bx, by)]
        if color == LIME:
            t.line(route, fill=INK, width=5)
            dashed_polyline(t, route, LIME, 3)
        else:
            dashed_polyline(t, route, COBALT, 3)
        for ex, ey in ((ax, ay), (bx, by)):
            s = 5
            t.rectangle([ex - s, ey - s, ex + s, ey + s], fill=color,
                        outline=INK, width=1)
    # Pins and badges.
    for num, _label, lat, lon, kind, color in MARKERS:
        px, py = proj.project(lon, lat)
        anchors[num] = (px, py)
        avoid.append((px, py))
        if kind == "pin":
            t.ellipse([px - 15, py - 15, px + 15, py + 15],
                      outline=VERMILION, width=2)
            t.ellipse([px - 9, py - 9, px + 9, py + 9], fill=VERMILION,
                      outline=(255, 255, 255), width=2)
        else:
            t.ellipse([px - 10, py - 10, px + 10, py + 10], fill=LIME,
                      outline=INK, width=2)
    chips = place_chips(t, anchors, avoid, w, h, forbidden=label_rects)
    for num, (rect, end) in chips.items():
        px, py = anchors[num]
        t.line([end[0], end[1], px, py], fill=INK, width=2)
    chip_font = font(SANS_B, 12)
    color_of = {m[0]: m[5] for m in MARKERS}
    color_of.update({a[0]: a[4] for a in ARCS})
    name_of = {m[0]: m[1] for m in MARKERS}
    name_of.update({a[0]: a[1] for a in ARCS})
    for num, (rect, _end) in chips.items():
        label = f"{num:02d} {name_of[num]}"
        t.rounded_rectangle(rect, radius=5, fill=(255, 255, 255),
                           outline=INK, width=2)
        t.rectangle([rect[0], rect[1], rect[0] + 5, rect[3]],
                    fill=color_of[num])
        t.text((rect[0] + 12, rect[1] + 4), label, font=chip_font, fill=INK)
    img.paste(tmp, (x0, y0))
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=INK, width=2)
    for num in sorted(anchors):
        px, py = anchors[num]
        print(f"anchor {num:02d}: map px ({px:.0f}, {py:.0f})")


# ---------------------------------------------------------------- zones 1+2
def draw_masthead(d):
    d.text((16, 14), "GLOBAL NEWS  /  DAILY WORLD BRIEF  /  17.11.2026",
           font=font(SANS_B, 14), fill=INK)
    right = "TUESDAY EDITION — VOL. 17 / 2026"
    rw = d.textlength(right, font=font(SANS_B, 14))
    d.text((803 - rw, 14), right, font=font(SANS_B, 14), fill=INK)
    title = "THE WORLD IN TENSION."
    title_font = fit_font(d, title, SANS_B, 66, 787, minimum=48)
    d.text((16, 40), title, font=title_font, fill=INK)
    d.rectangle([16, 118, 136, 128], fill=COBALT)
    d.text((148, 114), "7 STORIES. 5 REGIONS. ONE SHIFTING WORLD.",
           font=font(SANS_B, 14), fill=INK)
    d.line([16, 156, 803, 156], fill=INK, width=2)


def draw_map_header(d):
    d.text((16, 172), "01 / ", font=font(SANS_B, 16), fill=COBALT)
    w01 = d.textlength("01 / ", font=font(SANS_B, 16))
    d.text((16 + w01, 172), "THE GLOBAL MAP — GEOPOLITICAL SIGNALS",
           font=font(SANS_B, 16), fill=INK)


# ---------------------------------------------------------------- zone 3
CONFLICT = [
    ("01", "ASEAN UNDER PRESSURE",
     "49th ASEAN Summit opens in Manila as Trump arrives amid protests."),
    ("02", "KERCH BRIDGE HIT",
     "Ukrainian strikes severely damage the Kerch Bridge."),
    ("03", "HORMUZ ON EDGE",
     "Qeshm explosions and tanker attacks heighten Iran–US tensions."),
]
GRID = [
    ("TRADE", COBALT, "04 — $280M TARIFF SHIFT",
     "China and Canada agree to cut tariffs ahead of APEC."),
    ("TECH", LIME, "05 — AI CHIP CRACKDOWN",
     "US tightens chip licensing for five countries and investigates "
     "Singapore's Megaspeed."),
    ("TECH", LIME, "06 — NHS–PALANTIR EXIT",
     "UK government moves to end the NHS contract by 2029."),
    ("ENERGY", LIME, "07 — ASIA'S OIL SHIELD",
     "Japan proposes a regional pact for shared oil reserves."),
]


def draw_conflict_card(d, x, y, w, h, num, head, body):
    d.rectangle([x, y, x + w, y + h], fill=CARD_BG, outline=INK, width=2)
    d.rectangle([x, y, x + 6, y + h], fill=VERMILION)
    d.rectangle([x + 14, y + 12, x + 50, y + 48], fill=VERMILION)
    num_font = font(SANS_B, 20)
    tw = d.textlength(num, font=num_font)
    d.text((x + 32 - tw / 2, y + 19), num, font=num_font,
           fill=(255, 255, 255))
    head_font = font(SANS_B, 14)
    lines = wrap(d, head, head_font, w - 28)
    ly = y + 58
    for line in lines[:2]:
        d.text((x + 14, ly), line, font=head_font, fill=INK)
        ly += 18
    body_font = font(SANS, 11)
    for line in wrap(d, body, body_font, w - 28)[:3]:
        d.text((x + 14, ly + 4), line, font=body_font, fill=SUBINK)
        ly += 15


def draw_grid_card(d, x, y, w, h, tag, color, head, body):
    d.rectangle([x, y, x + w, y + h], fill=CARD_BG, outline=INK, width=2)
    d.rectangle([x, y, x + 6, y + h], fill=color)
    tag_font = font(SANS_B, 11)
    tw = d.textlength(tag, font=tag_font) + 18
    if color == LIME:
        d.rounded_rectangle([x + 16, y + 10, x + 16 + tw, y + 28], radius=9,
                            fill=LIME, outline=INK, width=2)
        d.text((x + 25, y + 13), tag, font=tag_font, fill=INK)
    else:
        d.rounded_rectangle([x + 16, y + 10, x + 16 + tw, y + 28], radius=9,
                            fill=COBALT)
        d.text((x + 25, y + 13), tag, font=tag_font, fill=(255, 255, 255))
    d.text((x + 16, y + 38), head, font=font(SANS_B, 14), fill=INK)
    body_font = font(SANS, 11)
    ly = y + 60
    for line in wrap(d, body, body_font, w - 32)[:2]:
        d.text((x + 16, ly), line, font=body_font, fill=SUBINK)
        ly += 15


def draw_zone3(d):
    d.text((16, 561), "02 / ", font=font(SANS_B, 16), fill=COBALT)
    w02 = d.textlength("02 / ", font=font(SANS_B, 16))
    d.text((16 + w02, 561), "SEVEN DEVELOPMENTS",
           font=font(SANS_B, 16), fill=INK)
    cw, chh = 257, 140
    for i, (num, head, body) in enumerate(CONFLICT):
        draw_conflict_card(d, 16 + i * (cw + 8), 590, cw, chh,
                           num, head, body)
    gw, gh = 389, 105
    for i, (tag, color, head, body) in enumerate(GRID):
        draw_grid_card(d, 16 + (i % 2) * (gw + 8),
                       738 + (i // 2) * (gh + 8), gw, gh,
                       tag, color, head, body)


# ---------------------------------------------------------------- zone 4
def draw_footer(d):
    d.line([16, 972, 803, 972], fill=INK, width=3)
    d.text((16, 986), "THE WORLD / DAILY BRIEF — 17 NOV 2026",
           font=font(SANS_B, 13), fill=INK)
    right = "CURATED GLOBAL INTELLIGENCE · @SEANNBEEZ"
    rw = d.textlength(right, font=font(SANS_B, 13))
    d.text((803 - rw, 986), right, font=font(SANS_B, 13), fill=INK)


def paper_grain(img, amp=2, tile=64):
    """Deterministic paper grain: a 64x64 tile of hash-based offsets
    (+/-amp brightness) repeated over the image, added last so the
    print-poster surface is not perfectly flat. Fully deterministic —
    the same tile every run — and subtle enough that no letter or line
    is affected visibly. Also gives the PNG the byte weight of a real
    printed texture instead of a flat vector fill."""
    from PIL import ImageChops
    t = Image.new("L", (tile, tile))
    px = t.load()
    for y in range(tile):
        for x in range(tile):
            h = (x * 2654435761 + y * 40503) & 0xFFFFFFFF
            h ^= h >> 13
            px[x, y] = 128 + (h % (2 * amp + 1)) - amp
    grain = Image.new("L", img.size)
    for gy in range(0, img.size[1], tile):
        for gx in range(0, img.size[0], tile):
            grain.paste(t, (gx, gy))
    return ImageChops.add(img, grain.convert("RGB"), 1.0, -128)


def main():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, W - 7, H - 7], outline=INK, width=3)

    draw_masthead(d)
    draw_map_header(d)
    draw_map(img, 16, 200, 787, 345)
    draw_zone3(d)
    draw_footer(d)

    img = paper_grain(img, amp=1, tile=32)
    img.save("entry.png", optimize=True)
    print("wrote entry.png", img.size,
          os.path.getsize("entry.png"), "bytes")


if __name__ == "__main__":
    main()
