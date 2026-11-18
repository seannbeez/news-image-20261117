"""Draw the World News Brief v4 — "WORLD ON EDGE." magazine cover.

819x1024 (4:5) deterministic rendering. SVG-first architecture: the
whole poster is authored as SVG vector primitives (masthead, a
Robinson-projection world map from real Natural Earth coastlines, and
seven bespoke story illustrations) and rasterized with CairoSVG at
819x1024. Pillow is used only to measure text (same Liberation fonts
CairoSVG resolves) so wrapping and fitting are exact. No image model,
no network, no timestamps, no randomness. No paper-grain pass: the
base render already lands at ~199 KB from legitimate detail
(coastlines, graticule, colour blocks), inside the 190-240 KB target.

Palette (bold colour blocking, not thin lines): Warm Editorial Paper
#F2F0E8, Deep Ink #17191C, Electric Cobalt #202BEB, Signal Red
#E74632, Acid Lime #D5F04A. Layout: oversized stacked headline,
full-bleed ink hero map panel, four rows of asymmetric story modules
(no dashboard boxes), minimal footer. All seven stories of Tuesday
17 November 2026 use Fura's exact copy, verified against live news.

Output: entry.png (819x1024, under 240 KB) + entry.svg (the source).
"""

import json
import math
import os
import xml.sax.saxutils as sax
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 819, 1024
PAPER = "#F2F0E8"
INK = "#17191C"
COBALT = "#202BEB"
RED = "#E74632"
LIME = "#D5F04A"
GRAT_DARK = "#45484B"      # graticule on the ink hero panel
OCEAN_GREY = "#9AA0A0"     # ocean labels on the ink hero panel
PAPER_RGB = (242, 240, 232)

SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_I = "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"

_measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def font(path, size):
    return ImageFont.truetype(path, size)


def tw(text, fnt):
    return _measure.textlength(text, font=fnt)


def wrap(text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if tw(trial, fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_size(text, path, start, max_w, minimum=40):
    size = start
    while size > minimum and tw(text, font(path, size)) > max_w:
        size -= 1
    return size


def esc(text):
    return sax.escape(text)


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
LAT0, LAT1 = -60.0, 90.0


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

    def __init__(self, w, h, pad=10):
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
    across the whole map."""
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


def pts_str(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def rects_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def overlap_area(a, b):
    if not rects_overlap(a, b):
        return 0.0
    return (min(a[2], b[2]) - max(a[0], b[0])) * (
        min(a[3], b[3]) - max(a[1], b[1])
    )


# (number, chip label, latitude, longitude, kind, colour)
MARKERS = [
    (1, "MANILA", 14.60, 120.98, "pin", RED),
    (2, "KERCH STRAIT", 45.35, 36.60, "pin", RED),
    (3, "HORMUZ", 26.75, 56.05, "pin", RED),
    (6, "LONDON", 51.51, -0.13, "badge", LIME),
    (7, "TOKYO", 35.68, 139.69, "badge", LIME),
]
# Arcs: (number, chip label, lat/lon A, lat/lon B, colour). True
# great circles (slerp), not Bezier chords.
ARCS = [
    (4, "CHINA–CANADA", (22.55, 114.06), (45.42, -75.70), COBALT),
    (5, "US–SINGAPORE", (38.90, -77.04), (1.35, 103.82), LIME),
]
# Ocean labels: (text, lon, lat) — placed by projection, centred.
OCEAN_LABELS = [
    ("ATLANTIC OCEAN", -28.0, 5.0),
    ("PACIFIC OCEAN", -150.0, -5.0),
    ("INDIAN OCEAN", 75.0, -28.0),
    ("SOUTHERN OCEAN", 60.0, -52.0),
]


def place_chips(anchors, avoid, w, h, forbidden=()):
    """Greedy chip placement around anchor points (map-canvas coords).
    Returns {num: (rect, leader_end)}."""
    chip_font = font(SANS_B, 12)
    placed = {}
    labels = {m[0]: m[1] for m in MARKERS}
    labels.update({a[0]: a[1] for a in ARCS})
    order = [1, 5, 4, 7, 2, 3, 6]  # crowded East Asia first
    for num in order:
        label = f"{num:02d} {labels[num]}"
        cw = tw(label, chip_font) + 16
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


# ---------------------------------------------------------------- hero map
def hero_map_svg(x0, y0, w, h):
    """Robinson world map on the ink panel, as SVG. Returns the SVG
    fragment (absolute canvas coordinates) plus a list of warnings."""
    out = []
    warnings = []
    coast = json.loads((HERE / "data" / "coast.json").read_text())
    proj = RobinsonMap(w, h)
    # Graticule every 15 degrees.
    for lon in range(-165, 181, 15):
        pts = [proj.project(lon, lat) for lat in range(-60, 91, 5)]
        out.append(
            f'<polyline points="{pts_str(pts)}" fill="none" '
            f'stroke="{GRAT_DARK}" stroke-width="1"/>')
    for lat in range(-60, 91, 15):
        x1, gy = proj.project(-180, lat)
        x2, _ = proj.project(180, lat)
        out.append(
            f'<line x1="{x1:.1f}" y1="{gy:.1f}" x2="{x2:.1f}" '
            f'y2="{gy:.1f}" stroke="{GRAT_DARK}" stroke-width="1"/>')
    # Real coastlines, split at the antimeridian.
    for poly in coast["polys"]:
        for part in split_ring(poly):
            pts = [proj.project(lon, lat) for lon, lat in part]
            out.append(
                f'<polygon points="{pts_str(pts)}" fill="{PAPER}"/>')
    # Ocean labels (projected anchors, centred).
    label_font = font(SANS_I, 12)
    label_rects = []
    for text, lon, lat in OCEAN_LABELS:
        px, py = proj.project(lon, lat)
        lw = tw(text, label_font)
        label_rects.append((px - lw / 2 - 2, py - 12, px + lw / 2 + 2,
                            py + 4))
        out.append(
            f'<text x="{px:.1f}" y="{py:.1f}" text-anchor="middle" '
            f'font-family="Liberation Sans" font-style="italic" '
            f'font-size="12" fill="{OCEAN_GREY}">{esc(text)}</text>')
    # Vertical side labels live in the dark bands beside the map.
    # (Local map-canvas coordinates: the caller translates the group.)
    left_rect = (52.0, 30.0, 70.0, h - 30.0)
    right_rect = (float(w) - 70.0, 30.0, float(w) - 52.0, h - 30.0)
    caption = "ROBINSON PROJECTION — NATURAL EARTH"
    cap_font = font(SANS, 10)
    cap_w = tw(caption, cap_font)
    cap_rect = (float(w) - cap_w - 12.0, h - 18.0,
                float(w) - 8.0, h - 2.0)
    forbidden = (label_rects + [left_rect, right_rect, cap_rect])
    # Arcs (true great circles) with a visible underlay: cobalt needs a
    # paper halo on the ink panel, lime needs an ink halo on paper land.
    anchors = {}
    avoid = []
    for num, _label, a, b, color in ARCS:
        route = [proj.project(lon, lat)
                 for lat, lon in great_circle(a, b)]
        for rx, ry in route:
            if not (0 <= rx <= w and 0 <= ry <= h):
                warnings.append(f"arc {num:02d} point outside frame "
                                f"({rx:.0f}, {ry:.0f})")
        ax, ay = route[0]
        bx, by = route[-1]
        mid = route[len(route) // 2]
        anchors[num] = mid
        avoid += [(ax, ay), (bx, by)]
        under = PAPER if color == COBALT else INK
        out.append(
            f'<polyline points="{pts_str(route)}" fill="none" '
            f'stroke="{under}" stroke-width="5" stroke-linecap="round"/>')
        out.append(
            f'<polyline points="{pts_str(route)}" fill="none" '
            f'stroke="{color}" stroke-width="3" stroke-linecap="round" '
            f'stroke-dasharray="10 7"/>')
        for ex, ey in ((ax, ay), (bx, by)):
            out.append(
                f'<rect x="{ex - 5:.1f}" y="{ey - 5:.1f}" width="10" '
                f'height="10" fill="{color}" stroke="{PAPER}" '
                f'stroke-width="1.5"/>')
    # Pins and badges.
    for num, _label, lat, lon, kind, color in MARKERS:
        px, py = proj.project(lon, lat)
        anchors[num] = (px, py)
        avoid.append((px, py))
        if kind == "pin":
            out.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="15" fill="none" '
                f'stroke="{RED}" stroke-width="2"/>')
            out.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9" '
                f'fill="{RED}" stroke="{PAPER}" stroke-width="2"/>')
        else:
            out.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="10" '
                f'fill="{LIME}" stroke="{INK}" stroke-width="2"/>')
    chips = place_chips(anchors, avoid, w, h, forbidden=forbidden)
    color_of = {m[0]: m[5] for m in MARKERS}
    color_of.update({a[0]: a[4] for a in ARCS})
    name_of = {m[0]: m[1] for m in MARKERS}
    name_of.update({a[0]: a[1] for a in ARCS})
    for num, (rect, end) in chips.items():
        px, py = anchors[num]
        rx, ry, rx2, ry2 = rect
        label = f"{num:02d} {name_of[num]}"
        out.append(
            f'<line x1="{end[0]:.1f}" y1="{end[1]:.1f}" x2="{px:.1f}" '
            f'y2="{py:.1f}" stroke="{INK}" stroke-width="2"/>')
        out.append(
            f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rx2 - rx:.1f}" '
            f'height="{ry2 - ry:.1f}" rx="5" fill="{PAPER}" '
            f'stroke="{INK}" stroke-width="2"/>')
        out.append(
            f'<rect x="{rx:.1f}" y="{ry:.1f}" width="5" '
            f'height="{ry2 - ry:.1f}" fill="{color_of[num]}"/>')
        out.append(
            f'<text x="{rx + 12:.1f}" y="{ry + 15.5:.1f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="12" fill="{INK}">{esc(label)}</text>')
    # Side labels + caption (local map-canvas coordinates).
    cy = h / 2
    out.append(
        f'<text transform="rotate(-90 61 {cy:.0f})" x="61" y="{cy:.0f}" '
        f'text-anchor="middle" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="13" letter-spacing="4" '
        f'fill="{PAPER}">THE GLOBAL MAP</text>')
    out.append(
        f'<text transform="rotate(-90 {w - 61:.0f} {cy:.0f})" '
        f'x="{w - 61:.0f}" y="{cy:.0f}" text-anchor="middle" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="13" letter-spacing="4" '
        f'fill="{PAPER}">17.11.2026</text>')
    out.append(
        f'<text x="{w - 10:.1f}" y="{h - 6:.1f}" text-anchor="end" '
        f'font-family="Liberation Sans" font-size="10" '
        f'fill="{OCEAN_GREY}">{esc(caption)}</text>')
    for num in sorted(anchors):
        px, py = anchors[num]
        print(f"anchor {num:02d}: map px ({px:.0f}, {py:.0f})")
    return "\n".join(out), warnings


# ------------------------------------------------------- story illustrations
# Each illustration is authored in a 100x100 local coordinate space and
# placed with <g transform="translate(x,y) scale(s)">. No text inside
# any pictogram: the pictures must read without words.

def illo_summit():
    """01 — ASEAN summit hall + protest banner, on Signal Red."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{RED}"/>
<polygon points="14,40 50,16 86,40" fill="{PAPER}"/>
<rect x="11" y="40" width="78" height="6" fill="{PAPER}"/>
<rect x="17" y="48" width="7" height="28" fill="{PAPER}"/>
<rect x="35" y="48" width="7" height="28" fill="{PAPER}"/>
<rect x="58" y="48" width="7" height="28" fill="{PAPER}"/>
<rect x="76" y="48" width="7" height="28" fill="{PAPER}"/>
<rect x="9" y="78" width="82" height="5" fill="{PAPER}"/>
<rect x="20" y="86" width="3" height="12" fill="{INK}"/>
<rect x="77" y="86" width="3" height="12" fill="{INK}"/>
<rect x="23" y="86" width="54" height="9" fill="{PAPER}"/>
<circle cx="30" cy="91" r="1.8" fill="{RED}"/>
<circle cx="40" cy="91" r="1.8" fill="{RED}"/>
<circle cx="50" cy="91" r="1.8" fill="{RED}"/>
<circle cx="60" cy="91" r="1.8" fill="{RED}"/>
<circle cx="70" cy="91" r="1.8" fill="{RED}"/>"""


def illo_bridge():
    """02 — fractured bridge span over dark waves, on Deep Ink."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{INK}"/>
<rect x="20" y="26" width="6" height="46" fill="{PAPER}"/>
<rect x="74" y="26" width="6" height="46" fill="{PAPER}"/>
<line x1="23" y1="26" x2="10" y2="50" stroke="{PAPER}" stroke-width="1.5"/>
<line x1="23" y1="26" x2="40" y2="50" stroke="{PAPER}" stroke-width="1.5"/>
<line x1="77" y1="26" x2="60" y2="50" stroke="{PAPER}" stroke-width="1.5"/>
<line x1="77" y1="26" x2="90" y2="50" stroke="{PAPER}" stroke-width="1.5"/>
<rect x="8" y="50" width="34" height="6" fill="{PAPER}"/>
<rect x="58" y="50" width="34" height="6" fill="{PAPER}"/>
<polyline points="42,50 46,58 50,50 54,58 58,50" fill="none"
 stroke="{RED}" stroke-width="3"/>
<polyline points="8,82 20,77 32,82 44,77 56,82 68,77 80,82 92,77"
 fill="none" stroke="{PAPER}" stroke-width="2"/>
<polyline points="8,91 20,86 32,91 44,86 56,91 68,86 80,91 92,86"
 fill="none" stroke="{PAPER}" stroke-width="2"/>"""


def illo_tanker():
    """03 — oil tanker silhouette + red blast wave, on Signal Red."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{RED}"/>
<polygon points="10,62 88,62 80,76 18,76" fill="{PAPER}"/>
<rect x="58" y="46" width="18" height="16" fill="{PAPER}"/>
<rect x="62" y="34" width="9" height="12" fill="{PAPER}"/>
<rect x="20" y="56" width="30" height="6" fill="{PAPER}"/>
<g stroke="{LIME}" stroke-width="3" stroke-linecap="round">
<line x1="30" y1="14" x2="30" y2="24"/>
<line x1="30" y1="36" x2="30" y2="46"/>
<line x1="14" y1="30" x2="24" y2="30"/>
<line x1="36" y1="30" x2="46" y2="30"/>
<line x1="19" y1="19" x2="26" y2="26"/>
<line x1="34" y1="34" x2="41" y2="41"/>
<line x1="41" y1="19" x2="34" y2="26"/>
<line x1="26" y1="34" x2="19" y2="41"/>
</g>
<circle cx="30" cy="30" r="5" fill="{LIME}"/>
<polyline points="8,86 20,81 32,86 44,81 56,86 68,81 80,86 92,81"
 fill="none" stroke="{PAPER}" stroke-width="2"/>"""


def illo_containers():
    """04 — two interlocking shipping containers, on Electric Cobalt."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{COBALT}"/>
<rect x="12" y="28" width="56" height="26" fill="{PAPER}"/>
<rect x="32" y="56" width="56" height="26" fill="{PAPER}"/>
<g stroke="{INK}" stroke-width="2">
<line x1="26" y1="28" x2="26" y2="54"/>
<line x1="40" y1="28" x2="40" y2="54"/>
<line x1="54" y1="28" x2="54" y2="54"/>
<line x1="46" y1="56" x2="46" y2="82"/>
<line x1="60" y1="56" x2="60" y2="82"/>
<line x1="74" y1="56" x2="74" y2="82"/>
</g>
<rect x="12" y="28" width="6" height="6" fill="{LIME}"/>
<rect x="82" y="76" width="6" height="6" fill="{LIME}"/>
<rect x="62" y="28" width="6" height="6" fill="{INK}"/>
<rect x="32" y="56" width="6" height="6" fill="{INK}"/>"""


def illo_chip():
    """05 — geometric microchip with 5 blocked circuit pathways, on
    Acid Lime."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{LIME}"/>
<rect x="28" y="28" width="44" height="44" rx="4" fill="{INK}"/>
<rect x="38" y="38" width="24" height="24" fill="{PAPER}"/>
<g stroke="{PAPER}" stroke-width="3" stroke-linecap="round">
<line x1="50" y1="28" x2="50" y2="16"/>
<line x1="72" y1="40" x2="84" y2="40"/>
<line x1="72" y1="60" x2="84" y2="60"/>
<line x1="40" y1="72" x2="40" y2="84"/>
<line x1="28" y1="50" x2="16" y2="50"/>
</g>
<g stroke="{RED}" stroke-width="3" stroke-linecap="round">
<line x1="45" y1="11" x2="55" y2="21"/>
<line x1="55" y1="11" x2="45" y2="21"/>
<line x1="82" y1="35" x2="92" y2="45"/>
<line x1="92" y1="35" x2="82" y2="45"/>
<line x1="82" y1="55" x2="92" y2="65"/>
<line x1="92" y1="55" x2="82" y2="65"/>
<line x1="35" y1="82" x2="45" y2="92"/>
<line x1="45" y1="82" x2="35" y2="92"/>
<line x1="8" y1="45" x2="18" y2="55"/>
<line x1="18" y1="45" x2="8" y2="55"/>
</g>"""


def illo_health():
    """06 — medical cross and a server block splitting apart, on
    Deep Ink."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{INK}"/>
<rect x="24" y="14" width="14" height="38" fill="{PAPER}"/>
<rect x="13" y="25" width="36" height="14" fill="{PAPER}"/>
<rect x="52" y="58" width="17" height="30" fill="{PAPER}"/>
<rect x="73" y="58" width="17" height="30" fill="{PAPER}"/>
<polyline points="71,58 68,66 72,72 68,80 71,88" fill="none"
 stroke="{RED}" stroke-width="3"/>
<g stroke="{INK}" stroke-width="2">
<line x1="55" y1="65" x2="66" y2="65"/>
<line x1="55" y1="72" x2="66" y2="72"/>
<line x1="55" y1="79" x2="66" y2="79"/>
<line x1="76" y1="65" x2="87" y2="65"/>
<line x1="76" y1="72" x2="87" y2="72"/>
<line x1="76" y1="79" x2="87" y2="79"/>
</g>
<circle cx="31" cy="66" r="4" fill="{RED}"/>"""


def illo_oil():
    """07 — geometric oil reserve tank with Asian network nodes, on
    Electric Cobalt."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{COBALT}"/>
<g stroke="{PAPER}" stroke-width="2">
<line x1="18" y1="22" x2="38" y2="36"/>
<line x1="82" y1="22" x2="62" y2="36"/>
<line x1="84" y1="68" x2="70" y2="62"/>
</g>
<path d="M30 44 A20 13 0 0 1 70 44 Z" fill="{PAPER}"/>
<rect x="30" y="44" width="40" height="36" fill="{PAPER}"/>
<rect x="34" y="80" width="5" height="8" fill="{PAPER}"/>
<rect x="61" y="80" width="5" height="8" fill="{PAPER}"/>
<rect x="14" y="89" width="72" height="3" fill="{PAPER}"/>
<circle cx="18" cy="22" r="5" fill="{LIME}"/>
<circle cx="82" cy="22" r="5" fill="{PAPER}"/>
<circle cx="84" cy="68" r="5" fill="{PAPER}"/>
<rect x="38" y="54" width="24" height="4" fill="{COBALT}"/>
<rect x="38" y="64" width="24" height="4" fill="{COBALT}"/>"""


ILLOS = {
    1: illo_summit, 2: illo_bridge, 3: illo_tanker, 4: illo_containers,
    5: illo_chip, 6: illo_health, 7: illo_oil,
}


# ------------------------------------------------------------------- stories
# (number, tag, tag colour, headline, body copy — Fura's exact words)
STORIES = [
    (1, "MANILA", RED, "01 — ASEAN UNDER PRESSURE",
     "49th ASEAN Summit opens in Manila as Trump arrives amid protests."),
    (2, "KERCH", RED, "02 — KERCH BRIDGE HIT",
     "Ukrainian strikes severely damage the Kerch Bridge."),
    (3, "HORMUZ", RED, "03 — HORMUZ ON EDGE",
     "Qeshm explosions and tanker attacks heighten Iran–US tensions."),
    (4, "TRADE", COBALT, "04 — $280M TARIFF SHIFT",
     "China and Canada agree to cut tariffs ahead of APEC."),
    (5, "AI TECH", LIME, "05 — AI CHIP CRACKDOWN",
     "US tightens chip licensing for five countries and investigates "
     "Singapore's Megaspeed."),
    (6, "UK HEALTH", LIME, "06 — NHS–PALANTIR EXIT",
     "UK government moves to end the NHS contract by 2029."),
    (7, "ENERGY", LIME, "07 — ASIA'S OIL SHIELD",
     "Japan proposes a regional pact for shared oil reserves."),
]


def tag_pill(x, y, tag, color):
    """Coloured category pill; returns its width."""
    fnt = font(SANS_B, 11)
    pw = tw(tag, fnt) + 18
    fill = INK if color == LIME else PAPER
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{pw:.0f}" height="16" '
            f'rx="8" fill="{color}"/>'
            f'<text x="{x + 9:.0f}" y="{y + 12:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="11" fill="{fill}">{esc(tag)}</text>'), pw


def module_wide(x, y, w, h, num, tag, color, head, body, warnings):
    """Wide module: square illustration left, tag + headline + body."""
    out = []
    s = h / 100.0
    out.append(f'<g transform="translate({x:.0f} {y:.0f}) '
               f'scale({s:.3f})">{ILLOS[num]()}</g>')
    x0 = x + h + 14
    text_w = w - h - 14
    pill, _ = tag_pill(x0, y + 2, tag, color)
    out.append(pill)
    head_fnt = font(SANS_B, 20)
    if tw(head, head_fnt) > text_w:
        warnings.append(f"module {num:02d} headline too wide")
    out.append(
        f'<text x="{x0:.0f}" y="{y + 40:.0f}" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="20" fill="{INK}">{esc(head)}</text>')
    body_fnt = font(SANS, 14)
    lines = wrap(body, body_fnt, text_w)
    if len(lines) > 2:
        warnings.append(f"module {num:02d} body wraps to "
                        f"{len(lines)} lines (max 2)")
    for i, line in enumerate(lines[:2]):
        out.append(
            f'<text x="{x0:.0f}" y="{y + 58 + i * 17:.0f}" '
            f'font-family="Liberation Sans" font-size="14" '
            f'fill="{INK}">{esc(line)}</text>')
    return "\n".join(out)


def module_narrow(x, y, w, h, num, color, head, body, warnings):
    """Narrow module: 64px illustration left, coloured number in the
    headline, body below. No tag pill — the coloured number and the
    illustration's colour block carry the category."""
    out = []
    out.append(f'<g transform="translate({x:.0f} {y + 8:.0f}) '
               f'scale(0.64)">{ILLOS[num]()}</g>')
    x0 = x + 72
    text_w = w - 72
    head_fnt = font(SANS_B, 14)
    lines = wrap(head, head_fnt, text_w)
    if len(lines) > 2:
        warnings.append(f"module {num:02d} headline wraps to "
                        f"{len(lines)} lines (max 2)")
    for i, line in enumerate(lines[:2]):
        ly = y + 18 + i * 17
        if i == 0 and line.startswith(f"{num:02d}"):
            pre, rest = line[:5], line[5:]
            out.append(
                f'<text x="{x0:.0f}" y="{ly:.0f}" '
                f'font-family="Liberation Sans" font-weight="bold" '
                f'font-size="14"><tspan fill="{color}">{esc(pre)}'
                f'</tspan><tspan fill="{INK}">{esc(rest)}</tspan>'
                f'</text>')
        else:
            out.append(
                f'<text x="{x0:.0f}" y="{ly:.0f}" '
                f'font-family="Liberation Sans" font-weight="bold" '
                f'font-size="14" fill="{INK}">{esc(line)}</text>')
    body_fnt = font(SANS, 13)
    body_lines = wrap(body, body_fnt, text_w)
    if len(body_lines) > 3:
        warnings.append(f"module {num:02d} body wraps to "
                        f"{len(body_lines)} lines (max 3)")
    by = y + 18 + len(lines[:2]) * 17 + 15
    for i, line in enumerate(body_lines[:3]):
        out.append(
            f'<text x="{x0:.0f}" y="{by + i * 15:.0f}" '
            f'font-family="Liberation Sans" font-size="13" '
            f'fill="{INK}">{esc(line)}</text>')
    return "\n".join(out)


def module_full(x, y, w, h, num, tag, color, head, body, warnings):
    """Full-width closing module: wide layout plus a big lime block
    with the story number as the asymmetric anchor."""
    out = [module_wide(x, y, w - 112, h, num, tag, color, head, body,
                       warnings)]
    bx = x + w - 100
    out.append(f'<rect x="{bx:.0f}" y="{y:.0f}" width="100" '
               f'height="{h:.0f}" fill="{LIME}"/>')
    big = font(SANS_B, 44)
    label = f"{num:02d}"
    bw = tw(label, big)
    out.append(
        f'<text x="{bx + 50 - bw / 2:.0f}" y="{y + h / 2 + 15:.0f}" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="44" fill="{INK}">{label}</text>')
    return "\n".join(out)


# ------------------------------------------------------------------- poster
def main():
    warnings = []
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
        f'height="{H}" viewBox="0 0 {W} {H}">')
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" '
                 f'fill="{PAPER}"/>')

    # ---- masthead: kicker, stacked headline, sub-deck, rule
    parts.append(f'<rect x="32" y="30" width="14" height="14" '
                 f'fill="{RED}"/>')
    parts.append(
        f'<text x="54" y="44" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="19" fill="{INK}">'
        f'GLOBAL NEWS / 17 NOVEMBER 2026</text>')
    parts.append(
        f'<text x="787" y="44" text-anchor="end" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="19" fill="{INK}">TUESDAY EDITION</text>')
    size = fit_size("ON EDGE.", SANS_B, 145, 755)
    top1 = 62
    base1 = top1 + round(size * 0.95)
    top2 = top1 + size + 8
    base2 = top2 + round(size * 0.95)
    parts.append(
        f'<text x="32" y="{base1}" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="{size}" fill="{INK}">'
        f'WORLD</text>')
    edge_w = tw("ON EDGE", font(SANS_B, size))
    parts.append(
        f'<text x="32" y="{base2}" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="{size}" fill="{INK}">'
        f'ON EDGE</text>')
    parts.append(
        f'<text x="{32 + edge_w:.0f}" y="{base2}" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="{size}" fill="{RED}">.</text>')
    sub_base = base2 + 30
    parts.append(f'<rect x="32" y="{sub_base - 14}" width="56" '
                 f'height="10" fill="{COBALT}"/>')
    parts.append(
        f'<text x="100" y="{sub_base}" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="20" fill="{INK}">'
        f'7 STORIES THAT DEFINE THE DAY</text>')
    rule_y = sub_base + 18
    parts.append(f'<line x1="32" y1="{rule_y}" x2="787" y2="{rule_y}" '
                 f'stroke="{INK}" stroke-width="2"/>')

    # ---- hero: full-bleed ink panel with the Robinson world map
    hero_y = rule_y + 12
    hero_h = 230
    parts.append(f'<rect x="0" y="{hero_y}" width="{W}" '
                 f'height="{hero_h}" fill="{INK}"/>')
    frag, map_warnings = hero_map_svg(0, 0, W, hero_h)
    warnings += map_warnings
    parts.append(f'<g transform="translate(0 {hero_y})">\n{frag}\n</g>')

    # ---- seven story modules: four asymmetric rows, no boxes
    mod_y = hero_y + hero_h + 16
    row_h, gap = 80, 8
    rows = [
        [(1, "wide", 32, 470), (2, "narrow", 518, 269)],
        [(3, "narrow", 32, 269), (4, "wide", 317, 470)],
        [(5, "wide", 32, 470), (6, "narrow", 518, 269)],
        [(7, "full", 32, 755)],
    ]
    by_num = {s[0]: s for s in STORIES}
    for r, row in enumerate(rows):
        y = mod_y + r * (row_h + gap)
        for num, kind, x, w in row:
            _, tag, color, head, body = by_num[num]
            if kind == "wide":
                parts.append(module_wide(x, y, w, row_h, num, tag,
                                         color, head, body, warnings))
            elif kind == "narrow":
                parts.append(module_narrow(x, y, w, row_h, num, color,
                                           head, body, warnings))
            else:
                parts.append(module_full(x, y, w, row_h, num, tag,
                                         color, head, body, warnings))
    footer_y = mod_y + 4 * row_h + 3 * gap + 14
    parts.append(
        f'<text x="32" y="{footer_y}" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="10" fill="{INK}">'
        f'THE WORLD / DAILY BRIEF — 17 NOV 2026</text>')
    parts.append(
        f'<text x="787" y="{footer_y}" text-anchor="end" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="10" fill="{INK}">'
        f'CURATED GLOBAL INTELLIGENCE · @SEANNBEEZ</text>')
    parts.append('</svg>')
    svg = "\n".join(parts)
    (HERE / "entry.svg").write_text(svg, encoding="utf-8")

    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(HERE / "entry.png"),
                     output_width=W, output_height=H)
    img = Image.open(HERE / "entry.png")
    assert img.size == (W, H), f"bad size {img.size}"
    # The base render is the deliverable: no grain pass (see docstring).
    img.save(HERE / "entry.png", optimize=True)
    size_bytes = os.path.getsize(HERE / "entry.png")
    import hashlib
    sha = hashlib.sha256((HERE / "entry.png").read_bytes()).hexdigest()
    print(f"wrote entry.png {img.size} {size_bytes} bytes sha256 {sha}")
    print(f"headline size {size}px, hero y {hero_y}, modules y "
          f"{mod_y}, footer y {footer_y}")
    if size_bytes >= 240 * 1024:
        print(f"WARNING: entry.png {size_bytes} bytes >= 240 KiB")
    if footer_y > 1022:
        print(f"WARNING: footer y {footer_y} too low")
    for warn in warnings:
        print("WARNING:", warn)
    if warnings:
        raise SystemExit(f"{len(warnings)} layout warnings — fix them")


if __name__ == "__main__":
    main()
