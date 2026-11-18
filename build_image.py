"""Draw the World News Brief v7 — dense 1024x1024 broadsheet.

Deterministic SVG-first rendering via CairoSVG at 1024x1024:
masthead, three illustrated hero banners, a dense 12-story editorial
grid (4 x 3), a Robinson-projection world map widget with numbered
pins, and a Key Themes & Daily Numbers panel. Pillow measures text
with the same Liberation fonts CairoSVG resolves, so wrapping and
fitting are exact. No image model, no network, no timestamps, no
randomness.

v7 is a surgical polish of v6 (Fura's three fixes): card 01 headline
and body unified on C$400M (~US$280M); the Key Themes panel rebuilt
as a balanced 3-column x 2-row executive stat grid with divider
rules; richer hero banners (data callout tags, horizon lines, subtle
shading bands). Every other fact, headline and figure is v6 as
verified.

Palette: warm newsprint #FAF8F3, dark navy #14213D, slate #2B4162,
crimson #C1121F, teal #1D6F72, pale-blue ocean #E3EEF5. All 15
stories (3 heroes + 12 grid) are Tuesday 17 November 2026 news
verified against live reporting; every figure on the poster comes
from the Phase 1 verification (see the builder's report).

Output: entry.png (1024x1024, target 200-240 KB, hard cap 1 MiB)
+ entry.svg (the source). If the base render exceeds 240 KB it is
first re-compressed losslessly with Zopfli (identical pixels, same
bytes out of main.py) and only if still over is it quantized to a
256-colour adaptive palette (deterministic, visually lossless on
this flat vector art) and re-saved.
"""

import hashlib
import json
import math
import os
import struct
import xml.sax.saxutils as sax
import zlib
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 1024, 1024
PAPER = "#FAF8F3"
INK = "#14213D"
SLATE = "#2B4162"
CRIMSON = "#C1121F"
TEAL = "#1D6F72"
OCEAN = "#E3EEF5"
CARD = "#FFFFFF"
SAND = "#E8DFCE"
GOLD = "#E8B93C"
AMBER = "#F2C879"
GREY = "#8A94A6"
GRAT = "#C3D5E2"
COASTLINE = "#9DB4C0"

SERIF_B = "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_I = "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"

_measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def font(path, size):
    return ImageFont.truetype(path, int(size))


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
    """Robinson projection fitted into a w x h box, equal scale."""

    def __init__(self, w, h, pad=4):
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


def pts_str(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def star_points(cx, cy, r_outer, r_inner, n=8):
    """Alternating-radius star polygon points (deterministic)."""
    pts = []
    for i in range(2 * n):
        r = r_outer if i % 2 == 0 else r_inner
        a = math.pi * i / n - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts_str(pts)


# ---------------------------------------------------------------- map widget
# (label, lat, lon, colour, dx, dy) — dx/dy offset the numbered pill
# from the true point; a leader line joins pill to a dot on the point.
# At this map scale London/Brussels and Shenzhen/Taoyuan/Manila sit
# only a few pixels apart, so clustered pins get leader pills instead
# of overlapping circles. dx=dy=0 means a numbered circle on the
# point itself (only New York is isolated enough for that).
MAP_PINS = [
    ("H1", 14.60, 120.98, CRIMSON, 17, 6),     # Manila — ASEAN
    ("H2", 45.35, 36.60, CRIMSON, 14, -29),    # Kerch Strait
    ("H3", 26.75, 56.05, CRIMSON, -20, 18),    # Hormuz
    ("05", 26.75, 56.05, CRIMSON, 21, -18),    # Hormuz oil prices
    ("01", 22.55, 114.06, INK, -24, 2),        # Shenzhen
    ("02", 1.35, 103.82, INK, -4, 16),         # Singapore
    ("03", 51.51, -0.13, INK, -29, -19),       # London (NHS)
    ("10", 51.51, -0.13, INK, 15, -17),        # London (Mexico-UK)
    ("04", 35.68, 139.69, INK, 10, -20),       # Tokyo
    ("06", 31.50, 34.47, INK, 32, 24),         # Gaza (ceasefire)
    ("12", 31.50, 34.47, INK, -50, 31),        # Gaza (winter aid)
    ("07", 50.85, 4.35, INK, -34, -2),         # Brussels
    ("08", 36.90, 30.71, INK, -36, -2),        # Antalya (COP31)
    ("09", 25.00, 121.30, INK, 13, 2),         # Taoyuan (Nvidia/Kinsus)
    ("11", 40.71, -74.01, INK, 0, 0),          # New York (Fed)
]


def map_widget_svg(x0, y0, w, h):
    """World map widget: pale-blue ocean, sand land from real Natural
    Earth coastlines, graticule, numbered pins. Local coordinates."""
    out = []
    out.append(f'<rect x="0" y="0" width="{w}" height="{h}" '
               f'fill="{OCEAN}"/>')
    out.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="none" '
               f'stroke="{INK}" stroke-width="1.5"/>')
    out.append(
        f'<text x="12" y="20" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="12" fill="{INK}">'
        f'THE GLOBAL MAP \u2014 12 HOTSPOTS</text>')
    mw, mh = w - 12, h - 44
    coast = json.loads((HERE / "data" / "coast.json").read_text())
    proj = RobinsonMap(mw, mh)
    inner = [f'<g transform="translate(6 28)">']
    for lon in range(-150, 181, 30):
        pts = [proj.project(lon, lat) for lat in range(-60, 91, 5)]
        inner.append(
            f'<polyline points="{pts_str(pts)}" fill="none" '
            f'stroke="{GRAT}" stroke-width="1"/>')
    for lat in range(-60, 91, 30):
        x1, gy = proj.project(-180, lat)
        x2, _ = proj.project(180, lat)
        inner.append(
            f'<line x1="{x1:.1f}" y1="{gy:.1f}" x2="{x2:.1f}" '
            f'y2="{gy:.1f}" stroke="{GRAT}" stroke-width="1"/>')
    for poly in coast["polys"]:
        for part in split_ring(poly):
            pts = [proj.project(lon, lat) for lon, lat in part]
            inner.append(
                f'<polygon points="{pts_str(pts)}" fill="{SAND}" '
                f'stroke="{COASTLINE}" stroke-width="0.6"/>')
    pin_fnt = font(SANS_B, 9)
    for label, lat, lon, color, dx, dy in MAP_PINS:
        px, py = proj.project(lon, lat)
        print(f"pin {label}: map px ({px:.0f}, {py:.0f})")
        if dx == 0 and dy == 0:
            inner.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="8.5" '
                f'fill="{color}" stroke="{PAPER}" stroke-width="1.5"/>')
            lw = tw(label, pin_fnt)
            inner.append(
                f'<text x="{px - lw / 2:.1f}" y="{py + 3.5:.1f}" '
                f'font-family="Liberation Sans" font-weight="bold" '
                f'font-size="9" fill="{PAPER}">{esc(label)}</text>')
        else:
            pw = tw(label, pin_fnt) + 10
            rx, ry = px + dx, py + dy
            cx, cy = rx + pw / 2, ry + 6
            inner.append(
                f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{cx:.1f}" '
                f'y2="{cy:.1f}" stroke="{INK}" stroke-width="1"/>')
            inner.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" '
                f'fill="{color}" stroke="{PAPER}" stroke-width="1"/>')
            inner.append(
                f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{pw:.1f}" '
                f'height="12" rx="3" fill="{color}"/>')
            lw = tw(label, pin_fnt)
            inner.append(
                f'<text x="{rx + 5:.1f}" y="{ry + 9:.1f}" '
                f'font-family="Liberation Sans" font-weight="bold" '
                f'font-size="9" fill="{PAPER}">{esc(label)}</text>')
    inner.append('</g>')
    out.append("\n".join(inner))
    out.append(
        f'<text x="12" y="{h - 8:.0f}" font-family="Liberation Sans" '
        f'font-size="9" fill="{SLATE}">'
        f'ROBINSON PROJECTION \u00b7 NATURAL EARTH \u00b7 '
        f'PINS H1\u2013H3, 01\u201312</text>')
    return f'<g transform="translate({x0} {y0})">\n' + "\n".join(out) + "\n</g>"

# ------------------------------------------------------- hero illustrations
# Each hero scene is authored directly in a 318x104 local space and
# placed with <g transform="translate(x,y)">. No text inside any
# scene: the pictures must read without words.

def scene_tag(x, y, text, fill):
    """Crisp data callout pill, sized to its measured text (9px bold).
    Used by the v7 hero banners; every tag's text is a verified
    17 November 2026 fact."""
    fnt = font(SANS_B, 9)
    w = tw(text, fnt) + 16
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="18" '
            f'rx="9" fill="{fill}"/>'
            f'<text x="{x + 8:.0f}" y="{y + 12.5:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="9" fill="{PAPER}">{esc(text)}</text>')


def scene_manila():
    """H1 — ASEAN summit hall, flags, protest crowd (warm amber sky).
    v7: data callout tag top-left, flags re-spaced right of it, sun
    tucked into the top-right corner, sky highlight band + darker
    ground band + horizon ticks for depth."""
    flags = "".join(
        f'<line x1="{x}" y1="10" x2="{x}" y2="34" stroke="{INK}" '
        f'stroke-width="2"/>'
        f'<rect x="{x}" y="8" width="16" height="10" fill="{c}"/>'
        for x, c in ((170, CRIMSON), (198, SLATE), (226, TEAL),
                     (254, GOLD), (282, PAPER)))
    heads = "".join(
        f'<circle cx="{x}" cy="95" r="5.5" fill="{INK}"/>'
        for x in range(16, 312, 30))
    placards = "".join(
        f'<rect x="{x - 7}" y="79" width="14" height="9" fill="{PAPER}" '
        f'stroke="{CRIMSON}" stroke-width="1.5"/>'
        for x in (46, 136, 226, 296))
    return f"""
<rect x="0" y="0" width="318" height="104" fill="{AMBER}"/>
<rect x="0" y="0" width="318" height="6" fill="{PAPER}" opacity="0.25"/>
<rect x="0" y="90" width="318" height="14" fill="#E3B968"/>
<line x1="0" y1="90" x2="40" y2="90" stroke="{INK}" stroke-width="1" opacity="0.25"/>
<line x1="278" y1="90" x2="318" y2="90" stroke="{INK}" stroke-width="1" opacity="0.25"/>
<circle cx="308" cy="14" r="8" fill="{CRIMSON}"/>
{scene_tag(8, 8, "MANILA \u00b7 ~2,000 PROTESTERS", INK)}
{flags}
<polygon points="40,58 159,30 278,58" fill="{INK}"/>
<rect x="40" y="54" width="238" height="5" fill="{PAPER}"/>
<rect x="40" y="58" width="238" height="30" fill="{INK}"/>
<rect x="56" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="92" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="128" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="164" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="200" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="236" y="62" width="10" height="22" fill="{PAPER}"/>
<rect x="40" y="88" width="238" height="4" fill="{PAPER}"/>
{placards}
{heads}"""


def scene_kerch():
    """H2 — fractured bridge span over dark waves, smoke plume.
    v7: data callout tag top-left, stars re-spaced right of it,
    smoke shifted right of the tag, horizon line at the waterline,
    sky highlight + deep-water shade for depth."""
    stars = "".join(
        f'<circle cx="{x}" cy="{y}" r="1.5" fill="{PAPER}"/>'
        for x, y in ((170, 7), (205, 12), (225, 6), (240, 9), (265, 16)))
    return f"""
<rect x="0" y="0" width="318" height="70" fill="{INK}"/>
<rect x="0" y="0" width="318" height="5" fill="{PAPER}" opacity="0.07"/>
{scene_tag(8, 6, "SPAN COLLAPSED \u00b7 2 KILLED", CRIMSON)}
{stars}
<rect x="0" y="70" width="318" height="34" fill="{SLATE}"/>
<line x1="0" y1="70" x2="318" y2="70" stroke="{PAPER}" stroke-width="1.5" opacity="0.85"/>
<rect x="0" y="96" width="318" height="8" fill="#0C1626" opacity="0.55"/>
<polyline points="0,84 20,80 40,84 60,80 80,84 100,80 120,84 140,80
 160,84 180,80 200,84 220,80 240,84 260,80 280,84 300,80 318,84"
 fill="none" stroke="{PAPER}" stroke-width="2" opacity="0.7"/>
<polyline points="0,95 20,91 40,95 60,91 80,95 100,91 120,95 140,91
 160,95 180,91 200,95 220,91 240,95 260,91 280,95 300,91 318,95"
 fill="none" stroke="{PAPER}" stroke-width="2" opacity="0.5"/>
<rect x="16" y="50" width="124" height="8" fill="{PAPER}"/>
<rect x="178" y="50" width="124" height="8" fill="{PAPER}"/>
<rect x="56" y="18" width="10" height="40" fill="{PAPER}"/>
<rect x="252" y="18" width="10" height="40" fill="{PAPER}"/>
<g stroke="{PAPER}" stroke-width="1.5">
<line x1="61" y1="18" x2="16" y2="50"/>
<line x1="61" y1="18" x2="140" y2="50"/>
<line x1="257" y1="18" x2="178" y2="50"/>
<line x1="257" y1="18" x2="302" y2="50"/>
</g>
<polyline points="140,50 148,58 152,50 158,60 164,52 170,58 178,50"
 fill="none" stroke="{CRIMSON}" stroke-width="4"/>
<circle cx="170" cy="36" r="9" fill="{GREY}" opacity="0.9"/>
<circle cx="183" cy="28" r="11" fill="{GREY}" opacity="0.9"/>
<circle cx="176" cy="18" r="8" fill="{GREY}" opacity="0.9"/>
<polygon points="288,8 300,28 276,28" fill="{CRIMSON}"/>
<rect x="287" y="14" width="2" height="7" fill="{PAPER}"/>
<circle cx="288" cy="24" r="1.2" fill="{PAPER}"/>"""


def scene_hormuz():
    """H3 — oil tanker in the strait, blast star, alert indicators.
    v7: data callout tag top-right, horizon line at the sky/sea
    boundary, sky highlight + deep-water shade, stern wake for
    depth."""
    return f"""
<rect x="0" y="0" width="318" height="42" fill="{OCEAN}"/>
<rect x="0" y="0" width="318" height="6" fill="{PAPER}" opacity="0.3"/>
{scene_tag(193, 8, "TANKER HIT \u00b7 HORMUZ", CRIMSON)}
<circle cx="40" cy="20" r="10" fill="{AMBER}"/>
<rect x="0" y="42" width="318" height="62" fill="{TEAL}"/>
<line x1="0" y1="42" x2="318" y2="42" stroke="{PAPER}" stroke-width="1.5" opacity="0.9"/>
<rect x="0" y="97" width="318" height="7" fill="{INK}" opacity="0.12"/>
<polyline points="0,56 20,52 40,56 60,52 80,56 100,52 120,56 140,52
 160,56 180,52 200,56 220,52 240,56 260,52 280,56 300,52 318,56"
 fill="none" stroke="{PAPER}" stroke-width="1.5" opacity="0.5"/>
<polyline points="0,96 20,92 40,96 60,92 80,96 100,92 120,96 140,92
 160,96 180,92 200,96 220,92 240,96 260,92 280,96 300,92 318,96"
 fill="none" stroke="{PAPER}" stroke-width="1.5" opacity="0.5"/>
<polyline points="8,90 20,88 32,90" fill="none" stroke="{PAPER}" stroke-width="1.5" opacity="0.6"/>
<polyline points="14,94 26,92 38,94" fill="none" stroke="{PAPER}" stroke-width="1.5" opacity="0.6"/>
<rect x="210" y="58" width="70" height="10" fill="{SLATE}"/>
<rect x="252" y="50" width="16" height="8" fill="{SLATE}"/>
<polygon points="36,68 282,68 266,88 52,88" fill="{INK}"/>
<rect x="206" y="50" width="44" height="18" fill="{PAPER}"/>
<rect x="212" y="54" width="8" height="6" fill="{INK}"/>
<rect x="226" y="54" width="8" height="6" fill="{INK}"/>
<rect x="240" y="54" width="8" height="6" fill="{INK}"/>
<rect x="238" y="40" width="10" height="12" fill="{CRIMSON}"/>
<circle cx="96" cy="28" r="32" fill="none" stroke="{PAPER}"
 stroke-width="1.5" opacity="0.5"/>
<circle cx="96" cy="28" r="24" fill="none" stroke="{PAPER}"
 stroke-width="1.5" opacity="0.5"/>
<polygon points="{star_points(96, 28, 18, 8)}" fill="{CRIMSON}"/>
<polygon points="{star_points(96, 28, 10, 5)}" fill="{AMBER}"/>
<polygon points="150,8 160,24 140,24" fill="{CRIMSON}"/>
<rect x="149" y="12" width="2" height="6" fill="{PAPER}"/>
<circle cx="150" cy="21" r="1.1" fill="{PAPER}"/>"""


# ------------------------------------------------------- grid illustrations
# Each illustration is authored in a 100x100 local coordinate space and
# placed with <g transform="translate(x,y) scale(0.46)">. No text
# inside any pictogram: the pictures must read without words.

def illo_containers():
    """01 — two interlocking shipping containers, on slate."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{SLATE}"/>
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
<rect x="12" y="28" width="6" height="6" fill="{GOLD}"/>
<rect x="82" y="76" width="6" height="6" fill="{GOLD}"/>
<rect x="62" y="28" width="6" height="6" fill="{INK}"/>
<rect x="32" y="56" width="6" height="6" fill="{INK}"/>"""


def illo_chip():
    """02 — geometric microchip with 5 blocked circuit pathways, on
    teal."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{TEAL}"/>
<rect x="28" y="28" width="44" height="44" rx="4" fill="{INK}"/>
<rect x="38" y="38" width="24" height="24" fill="{PAPER}"/>
<g stroke="{PAPER}" stroke-width="3" stroke-linecap="round">
<line x1="50" y1="28" x2="50" y2="16"/>
<line x1="72" y1="40" x2="84" y2="40"/>
<line x1="72" y1="60" x2="84" y2="60"/>
<line x1="40" y1="72" x2="40" y2="84"/>
<line x1="28" y1="50" x2="16" y2="50"/>
</g>
<g stroke="{CRIMSON}" stroke-width="3" stroke-linecap="round">
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
    """03 — medical cross and a server block splitting apart, on
    navy."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{INK}"/>
<rect x="24" y="14" width="14" height="38" fill="{PAPER}"/>
<rect x="13" y="25" width="36" height="14" fill="{PAPER}"/>
<rect x="48" y="58" width="17" height="30" fill="{PAPER}"/>
<rect x="78" y="58" width="17" height="30" fill="{PAPER}"/>
<polyline points="73,58 69,66 74,72 69,80 73,88" fill="none"
 stroke="{CRIMSON}" stroke-width="4"/>
<g stroke="{INK}" stroke-width="2">
<line x1="51" y1="65" x2="62" y2="65"/>
<line x1="51" y1="72" x2="62" y2="72"/>
<line x1="51" y1="79" x2="62" y2="79"/>
<line x1="81" y1="65" x2="92" y2="65"/>
<line x1="81" y1="72" x2="92" y2="72"/>
<line x1="81" y1="79" x2="92" y2="79"/>
</g>
<circle cx="31" cy="66" r="4" fill="{CRIMSON}"/>"""


def illo_oil():
    """04 — geometric oil reserve tank with Asian network nodes, on
    slate."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{SLATE}"/>
<g stroke="{PAPER}" stroke-width="2">
<line x1="18" y1="22" x2="38" y2="36"/>
<line x1="82" y1="22" x2="62" y2="36"/>
<line x1="84" y1="68" x2="70" y2="62"/>
<line x1="16" y1="68" x2="30" y2="66"/>
</g>
<path d="M30 44 A20 13 0 0 1 70 44 Z" fill="{PAPER}"/>
<rect x="30" y="44" width="40" height="36" fill="{PAPER}"/>
<rect x="34" y="80" width="5" height="8" fill="{PAPER}"/>
<rect x="61" y="80" width="5" height="8" fill="{PAPER}"/>
<rect x="14" y="89" width="72" height="3" fill="{PAPER}"/>
<circle cx="18" cy="22" r="5" fill="{GOLD}"/>
<circle cx="82" cy="22" r="5" fill="{PAPER}"/>
<circle cx="84" cy="68" r="5" fill="{PAPER}"/>
<circle cx="16" cy="68" r="5" fill="{GOLD}"/>
<rect x="38" y="54" width="24" height="4" fill="{SLATE}"/>
<rect x="38" y="64" width="24" height="4" fill="{SLATE}"/>"""


def illo_barrel():
    """05 — oil barrel with a rising price arrow, on crimson."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{CRIMSON}"/>
<rect x="22" y="32" width="40" height="46" rx="6" fill="{PAPER}"/>
<rect x="22" y="44" width="40" height="4" fill="{CRIMSON}"/>
<rect x="22" y="62" width="40" height="4" fill="{CRIMSON}"/>
<polyline points="72,84 72,40" fill="none" stroke="{TEAL}"
 stroke-width="6" stroke-linecap="round"/>
<polyline points="62,50 72,36 82,50" fill="none" stroke="{TEAL}"
 stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
<polyline points="8,92 20,87 32,92 44,87 56,92 68,87 80,92 92,87"
 fill="none" stroke="{PAPER}" stroke-width="2"/>"""


def illo_dove():
    """06 — peace dove over an olive branch, on teal."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{TEAL}"/>
<ellipse cx="48" cy="52" rx="20" ry="11" fill="{PAPER}"
 transform="rotate(-18 48 52)"/>
<ellipse cx="46" cy="48" rx="12" ry="6" fill="{AMBER}"
 transform="rotate(-18 46 48)"/>
<circle cx="66" cy="40" r="7" fill="{PAPER}"/>
<polygon points="72,38 80,41 72,44" fill="{GOLD}"/>
<g stroke="{PAPER}" stroke-width="3" stroke-linecap="round">
<line x1="30" y1="58" x2="16" y2="52"/>
<line x1="30" y1="58" x2="14" y2="58"/>
<line x1="30" y1="58" x2="16" y2="64"/>
</g>
<line x1="18" y1="86" x2="82" y2="86" stroke="{INK}" stroke-width="2"/>
<ellipse cx="30" cy="82" rx="6" ry="2.5" fill="{PAPER}"
 transform="rotate(-25 30 82)"/>
<ellipse cx="44" cy="80" rx="6" ry="2.5" fill="{PAPER}"
 transform="rotate(-25 44 80)"/>
<ellipse cx="58" cy="82" rx="6" ry="2.5" fill="{PAPER}"
 transform="rotate(25 58 82)"/>
<ellipse cx="72" cy="80" rx="6" ry="2.5" fill="{PAPER}"
 transform="rotate(25 72 80)"/>"""


def illo_shield():
    """07 — EU shield ringed by stars, on navy."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{INK}"/>
<path d="M50 10 L84 22 V52 C84 72 68 86 50 92 C32 86 16 72 16 52 V22 Z"
 fill="{SLATE}" stroke="{GOLD}" stroke-width="3"/>
<path d="M50 18 L76 28 V52 C76 67 64 78 50 83 C36 78 24 67 24 52 V28 Z"
 fill="none" stroke="{GOLD}" stroke-width="1.5"/>
<circle cx="50" cy="34" r="2.2" fill="{GOLD}"/>
<circle cx="62" cy="40" r="2.2" fill="{GOLD}"/>
<circle cx="66" cy="52" r="2.2" fill="{GOLD}"/>
<circle cx="62" cy="64" r="2.2" fill="{GOLD}"/>
<circle cx="50" cy="70" r="2.2" fill="{GOLD}"/>
<circle cx="38" cy="64" r="2.2" fill="{GOLD}"/>
<circle cx="34" cy="52" r="2.2" fill="{GOLD}"/>
<circle cx="38" cy="40" r="2.2" fill="{GOLD}"/>"""


def illo_globe():
    """08 — globe with a leaf, on teal (climate)."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{TEAL}"/>
<circle cx="50" cy="46" r="30" fill="{PAPER}"/>
<ellipse cx="50" cy="46" rx="12" ry="30" fill="none" stroke="{TEAL}"
 stroke-width="2"/>
<line x1="20" y1="46" x2="80" y2="46" stroke="{TEAL}" stroke-width="2"/>
<ellipse cx="42" cy="34" rx="9" ry="5" fill="{TEAL}"
 transform="rotate(-20 42 34)"/>
<ellipse cx="60" cy="58" rx="8" ry="5" fill="{TEAL}"
 transform="rotate(15 60 58)"/>
<ellipse cx="70" cy="78" rx="11" ry="5" fill="{GOLD}"
 transform="rotate(-30 70 78)"/>
<line x1="62" y1="84" x2="56" y2="90" stroke="{GOLD}" stroke-width="2"/>
<rect x="44" y="78" width="12" height="4" fill="{PAPER}"/>
<rect x="36" y="84" width="28" height="4" fill="{PAPER}"/>"""


def illo_factory():
    """09 — chip on a factory conveyor, on slate (supply chain)."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{SLATE}"/>
<rect x="24" y="18" width="36" height="36" rx="4" fill="{INK}"/>
<rect x="32" y="26" width="20" height="20" fill="{PAPER}"/>
<g stroke="{PAPER}" stroke-width="2.5" stroke-linecap="round">
<line x1="42" y1="18" x2="42" y2="10"/>
<line x1="60" y1="30" x2="68" y2="30"/>
<line x1="60" y1="42" x2="68" y2="42"/>
<line x1="36" y1="54" x2="36" y2="62"/>
<line x1="24" y1="36" x2="16" y2="36"/>
</g>
<circle cx="80" cy="30" r="10" fill="none" stroke="{GOLD}"
 stroke-width="3"/>
<g stroke="{GOLD}" stroke-width="2.5">
<line x1="80" y1="16" x2="80" y2="24"/>
<line x1="80" y1="36" x2="80" y2="44"/>
<line x1="66" y1="30" x2="74" y2="30"/>
<line x1="86" y1="30" x2="94" y2="30"/>
</g>
<rect x="14" y="72" width="72" height="8" fill="{INK}"/>
<rect x="20" y="56" width="14" height="14" fill="{PAPER}"/>
<rect x="20" y="61" width="14" height="3" fill="{TEAL}"/>
<rect x="42" y="56" width="14" height="14" fill="{PAPER}"/>
<rect x="42" y="61" width="14" height="3" fill="{TEAL}"/>
<rect x="64" y="56" width="14" height="14" fill="{PAPER}"/>
<rect x="64" y="61" width="14" height="3" fill="{TEAL}"/>"""


def illo_flags():
    """10 — Mexico and UK flags on poles, on crimson."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{CRIMSON}"/>
<line x1="28" y1="10" x2="28" y2="90" stroke="{PAPER}" stroke-width="3"/>
<rect x="28" y="10" width="11" height="20" fill="{TEAL}"/>
<rect x="39" y="10" width="11" height="20" fill="{PAPER}"/>
<rect x="50" y="10" width="11" height="20" fill="{CRIMSON}"
 stroke="{PAPER}" stroke-width="1"/>
<line x1="72" y1="10" x2="72" y2="90" stroke="{PAPER}" stroke-width="3"/>
<rect x="72" y="10" width="24" height="20" fill="{INK}"/>
<rect x="82" y="10" width="4" height="20" fill="{PAPER}"/>
<rect x="72" y="18" width="24" height="4" fill="{PAPER}"/>
<rect x="83" y="10" width="2" height="20" fill="{CRIMSON}"/>
<rect x="72" y="19" width="24" height="2" fill="{CRIMSON}"/>
<rect x="8" y="92" width="84" height="3" fill="{PAPER}"/>"""


def illo_bank():
    """11 — classical bank building with a rising rate arrow, on
    navy."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{INK}"/>
<polygon points="18,34 50,16 82,34" fill="{PAPER}"/>
<rect x="24" y="38" width="6" height="34" fill="{PAPER}"/>
<rect x="38" y="38" width="6" height="34" fill="{PAPER}"/>
<rect x="56" y="38" width="6" height="34" fill="{PAPER}"/>
<rect x="70" y="38" width="6" height="34" fill="{PAPER}"/>
<rect x="16" y="72" width="68" height="6" fill="{PAPER}"/>
<rect x="12" y="80" width="76" height="4" fill="{PAPER}"/>
<polyline points="90,70 90,38" fill="none" stroke="{CRIMSON}"
 stroke-width="5" stroke-linecap="round"/>
<polyline points="83,46 90,36 97,46" fill="none" stroke="{CRIMSON}"
 stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>"""


def illo_tent():
    """12 — aid tent under falling snow, on slate."""
    return f"""
<rect x="0" y="0" width="100" height="100" fill="{SLATE}"/>
<polygon points="14,78 50,34 86,78" fill="{PAPER}"/>
<polygon points="42,78 50,58 58,78" fill="{INK}"/>
<g stroke="{PAPER}" stroke-width="2" stroke-linecap="round">
<line x1="20" y1="16" x2="20" y2="26"/>
<line x1="15" y1="21" x2="25" y2="21"/>
<line x1="16.5" y1="17.5" x2="23.5" y2="24.5"/>
<line x1="23.5" y1="17.5" x2="16.5" y2="24.5"/>
<line x1="78" y1="12" x2="78" y2="22"/>
<line x1="73" y1="17" x2="83" y2="17"/>
<line x1="74.5" y1="13.5" x2="81.5" y2="20.5"/>
<line x1="81.5" y1="13.5" x2="74.5" y2="20.5"/>
<line x1="88" y1="48" x2="88" y2="58"/>
<line x1="83" y1="53" x2="93" y2="53"/>
<line x1="84.5" y1="49.5" x2="91.5" y2="56.5"/>
<line x1="91.5" y1="49.5" x2="84.5" y2="56.5"/>
</g>
<rect x="8" y="82" width="84" height="4" fill="{PAPER}"/>"""


ILLOS = {
    1: illo_containers, 2: illo_chip, 3: illo_health, 4: illo_oil,
    5: illo_barrel, 6: illo_dove, 7: illo_shield, 8: illo_globe,
    9: illo_factory, 10: illo_flags, 11: illo_bank, 12: illo_tent,
}

# ------------------------------------------------------------------- stories
# (number, tag, tag colour, headline, body copy — every fact verified
# against live 17 November 2026 reporting; see the builder's report.)
HEROES = [
    (1, "GEOPOLITICS", CRIMSON,
     "49th ASEAN Summit Opens in Manila as Trump Arrives",
     "ASEAN leaders open the 49th summit in Manila as protests greet "
     "Trump's arrival.",
     scene_manila),
    (2, "CONFLICT", CRIMSON,
     "Ukrainian Strike Severely Damages Kerch Bridge",
     "The strike collapses a span and halts traffic; two killed, "
     "officials say.",
     scene_kerch),
    (3, "MIDDLE EAST", CRIMSON,
     "Qeshm Blasts & Tanker Attacks Rock Hormuz",
     "Blasts rock Qeshm Island and tankers are hit in the strait, "
     "raising fears of a wider clash.",
     scene_hormuz),
]

STORIES = [
    (1, "TRADE", SLATE, "China\u2013Canada Cut C$400M Tariffs",
     "Ottawa and Beijing agree C$400M (~US$280M) in tariff cuts on "
     "pork and seafood ahead of APEC in Shenzhen."),
    (2, "TECH", TEAL, "US Curbs AI Chips in 5 Nations",
     "Licences now required for advanced chips to five nations; "
     "Megaspeed faces a criminal probe."),
    (3, "UK", CRIMSON, "UK Ends NHS Palantir Deal by 2029",
     "The NHS data-platform contract with Palantir ends in March "
     "2029; the break clause was skipped."),
    (4, "ENERGY", TEAL, "Japan Proposes Asian Oil Pact",
     "Tokyo proposes an Asia oil security task force \u2014 an Asian "
     "IEA \u2014 at the Manila summit."),
    (5, "MARKETS", CRIMSON, "Brent Jumps to $93.14 a Barrel",
     "Brent settles up $0.70 at $93.14; WTI gains $0.29 to $86.01 as "
     "Hormuz transit falls by half."),
    (6, "DIPLOMACY", SLATE, "Gaza Ceasefire Warning at UN",
     "The Board of Peace warns the UN the Gaza ceasefire \u2018cannot "
     "be sustained\u2019 without visible gains."),
    (7, "EUROPE", INK, "EU Defence Ministers Meet in Brussels",
     "Kallas chairs talks on Ukraine air defence; Kyiv\u2019s Khmara "
     "and the US\u2019s Colby join the session."),
    (8, "CLIMATE", TEAL, "COP31 Draft Deal Divides Ministers",
     "An 18-page draft in Antalya seeks a fossil-fuel shift and "
     "$120B yearly adaptation finance by 2035."),
    (9, "TECH", SLATE, "Nvidia Locks In AI Supply Chain",
     "Nvidia signs multiyear deals with Kinsus, SPIL and Samsung; "
     "Kinsus lifts substrate capacity 3.5\u00d7."),
    (10, "LATAM", CRIMSON, "Mexico\u2013UK Summit Meets in London",
     "London hosts a Mexico\u2013UK summit on trade after Mexico "
     "ratified the UK\u2019s CPTPP accession."),
    (11, "ECONOMY", INK, "Fed\u2019s Williams: Rates May Rise",
     "New York Fed chief Williams says the Fed could keep raising "
     "rates; funds rate stands at 3.75\u20134.00%."),
    (12, "AID", TEAL, "Winter Aid Warning for Gaza",
     "WFP and IOM warn 1.7M Gazans are displaced and 1.4M face acute "
     "hunger; IOM is $173M short."),
]

# (big number, label, colour) for the Key Themes panel, in
# column-major order: col 1 C$400M / 49th, col 2 $93.14 / 5,
# col 3 2029 / $120B/yr. Every figure matches the cards above.
STATS = [
    ("C$400M", "China\u2013Canada tariff cuts", CRIMSON),
    ("$93.14", "Brent crude, Tuesday close", TEAL),
    ("2029", "NHS\u2013Palantir contract ends", CRIMSON),
    ("49th", "ASEAN Summit in Manila", INK),
    ("5", "Nations under AI chip curbs", INK),
    ("$120B/yr", "COP31 adaptation goal by 2035", TEAL),
]

# Card 01's body is one line longer than the others once the
# (~US$280M) conversion is added; 12.5pt keeps it at 3 lines
# (measured: 183/200/201px at 12.5pt vs 4 lines at 13pt).
BODY_SIZE = {1: 12.5}


def tag_pill(x, y, tag, color):
    """Coloured category pill; returns its width."""
    fnt = font(SANS_B, 11)
    pw = tw(tag, fnt) + 18
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{pw:.0f}" height="16" '
            f'rx="8" fill="{color}"/>'
            f'<text x="{x + 9:.0f}" y="{y + 12:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="11" fill="{PAPER}">{esc(tag)}</text>'), pw


def hero_card(x, y, w, h, num, tag, color, head, body, scene_fn,
              warnings):
    """Hero banner: full-width scene, tag pill, bold title, 2-line
    summary."""
    out = []
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="{h:.0f}" fill="{CARD}" stroke="{INK}" '
               f'stroke-width="1.5"/>')
    out.append(f'<g transform="translate({x:.0f} {y:.0f})">'
               f'{scene_fn()}</g>')
    pill, _ = tag_pill(x + 10, y + 112, f"H{num} \u00b7 {tag}", color)
    out.append(pill)
    head_fnt = font(SANS_B, 19)
    lines = wrap(head, head_fnt, w - 20)
    if len(lines) > 2:
        warnings.append(f"hero {num} headline wraps to "
                        f"{len(lines)} lines (max 2)")
    for i, line in enumerate(lines[:2]):
        out.append(
            f'<text x="{x + 10:.0f}" y="{y + 150 + i * 21:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="19" fill="{INK}">{esc(line)}</text>')
    body_fnt = font(SANS, 13)
    body_lines = wrap(body, body_fnt, w - 20)
    if len(body_lines) > 2:
        warnings.append(f"hero {num} body wraps to "
                        f"{len(body_lines)} lines (max 2)")
    for i, line in enumerate(body_lines[:2]):
        out.append(
            f'<text x="{x + 10:.0f}" y="{y + 190 + i * 14:.0f}" '
            f'font-family="Liberation Sans" font-size="13" '
            f'fill="{SLATE}">{esc(line)}</text>')
    return "\n".join(out)


def grid_card(x, y, w, h, num, tag, color, head, body, warnings):
    """Dense grid card: colour top bar, tag, 46px illustration badge,
    bold 2-line headline, 3-line factual summary."""
    out = []
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="{h:.0f}" fill="{CARD}" stroke="{INK}" '
               f'stroke-width="1.5"/>')
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="5" fill="{color}"/>')
    out.append(
        f'<text x="{x + 10:.0f}" y="{y + 24:.0f}" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="10" letter-spacing="1" fill="{color}">'
        f'{num:02d} \u00b7 {esc(tag)}</text>')
    out.append(f'<g transform="translate({x + 10:.0f} {y + 32:.0f}) '
               f'scale(0.46)">{ILLOS[num]()}</g>')
    head_fnt = font(SANS_B, 15)
    lines = wrap(head, head_fnt, w - 74)
    if len(lines) > 2:
        warnings.append(f"card {num:02d} headline wraps to "
                        f"{len(lines)} lines (max 2)")
    for i, line in enumerate(lines[:2]):
        out.append(
            f'<text x="{x + 64:.0f}" y="{y + 48 + i * 17:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="15" fill="{INK}">{esc(line)}</text>')
    body_fnt = font(SANS, BODY_SIZE.get(num, 13))
    body_lines = wrap(body, body_fnt, w - 20)
    if len(body_lines) > 3:
        warnings.append(f"card {num:02d} body wraps to "
                        f"{len(body_lines)} lines (max 3)")
    for i, line in enumerate(body_lines[:3]):
        out.append(
            f'<text x="{x + 10:.0f}" y="{y + 96 + i * 15:.0f}" '
            f'font-family="Liberation Sans" '
            f'font-size="{BODY_SIZE.get(num, 13)}" '
            f'fill="{INK}">{esc(line)}</text>')
    return "\n".join(out)


def key_themes_panel(x, y, w, h):
    """Key Themes & Daily Numbers: balanced 3-column x 2-row
    executive stat grid with subtle divider rules, closing line +
    footer. v7: the two-column layout left a wide empty gap in the
    middle; three columns fill it."""
    out = []
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="{h:.0f}" fill="{CARD}" stroke="{INK}" '
               f'stroke-width="1.5"/>')
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="5" fill="{INK}"/>')
    out.append(
        f'<text x="{x + 16:.0f}" y="{y + 26:.0f}" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="15" fill="{INK}">'
        f'KEY THEMES &amp; DAILY NUMBERS</text>')
    col_w = (w - 32) / 3
    for cx in (x + 16 + col_w, x + 16 + 2 * col_w):
        out.append(f'<line x1="{cx:.1f}" y1="{y + 46:.0f}" '
                   f'x2="{cx:.1f}" y2="{y + 136:.0f}" '
                   f'stroke="{GRAT}" stroke-width="1"/>')
    out.append(f'<line x1="{x + 16:.0f}" y1="{y + 89:.0f}" '
               f'x2="{x + w - 16:.0f}" y2="{y + 89:.0f}" '
               f'stroke="{GRAT}" stroke-width="1"/>')
    for i, (num, label, color) in enumerate(STATS):
        col, row = i % 3, i // 3
        cx = x + 16 + col * col_w
        ry = y + 40 + row * 56
        out.append(
            f'<text x="{cx:.0f}" y="{ry + 24:.0f}" '
            f'font-family="Liberation Sans" font-weight="bold" '
            f'font-size="21" fill="{color}">{esc(num)}</text>')
        out.append(
            f'<text x="{cx:.0f}" y="{ry + 42:.0f}" '
            f'font-family="Liberation Sans" font-size="11" '
            f'fill="{SLATE}">{esc(label)}</text>')
    out.append(f'<line x1="{x + 16:.0f}" y1="{y + 158:.0f}" '
               f'x2="{x + w - 16:.0f}" y2="{y + 158:.0f}" '
               f'stroke="{SLATE}" stroke-width="1"/>')
    out.append(
        f'<text x="{x + 16:.0f}" y="{y + 172:.0f}" '
        f'font-family="Liberation Sans" font-style="italic" '
        f'font-size="11" fill="{SLATE}">'
        f'15 stories \u00b7 3 flashpoints \u00b7 12 in depth \u2014 every '
        f'figure verified from 17 Nov 2026 reporting.</text>')
    out.append(
        f'<text x="{x + w - 16:.0f}" y="{y + 187:.0f}" '
        f'text-anchor="end" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="11" fill="{INK}">'
        f'@seannbeez \u00b7 17 November 2026</text>')
    return "\n".join(out)


def zopfli_pass(path):
    """Lossless re-compression of the PNG's IDAT with Zopfli: the
    filtered scanlines are re-compressed with a better DEFLATE
    search, so the file shrinks with identical pixels. Returns the
    new size, or None when the zopfli module is unavailable (the
    caller then falls back to the palette pass). Deterministic."""
    try:
        import zopfli.zlib as zz
    except ImportError:
        return None
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks, idat = 8, [], b""
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        chunks.append((typ, body))
        if typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    comp = zz.compress(raw, numiterations=15)
    out = bytearray(data[:8])
    for typ, body in chunks:
        if typ == b"IDAT":
            continue
        out += struct.pack(">I4s", len(body), typ) + body
        out += struct.pack(">I", zlib.crc32(typ + body) & 0xffffffff)
        if typ == b"IHDR":
            for i in range(0, len(comp), 65536):
                piece = comp[i:i + 65536]
                out += struct.pack(">I4s", len(piece), b"IDAT") + piece
                out += struct.pack(
                    ">I", zlib.crc32(b"IDAT" + piece) & 0xffffffff)
    path.write_bytes(bytes(out))
    return len(out)


# ------------------------------------------------------------------- poster
def main():
    warnings = []
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
        f'height="{H}" viewBox="0 0 {W} {H}">')
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" '
                 f'fill="{PAPER}"/>')

    # ---- masthead: kicker, serif title, subtitle, double rule
    parts.append(
        f'<text x="24" y="40" font-family="Liberation Sans" '
        f'font-weight="bold" font-size="13" letter-spacing="2" '
        f'fill="{INK}">TUESDAY \u00b7 17 NOVEMBER 2026</text>')
    parts.append(
        f'<text x="1000" y="40" text-anchor="end" '
        f'font-family="Liberation Sans" font-weight="bold" '
        f'font-size="13" letter-spacing="2" fill="{INK}">'
        f'15 STORIES \u00b7 5 REGIONS</text>')
    title = "The World on 17 November 2026"
    size = fit_size(title, SERIF_B, 56, 976)
    parts.append(
        f'<text x="24" y="92" font-family="Liberation Serif" '
        f'font-weight="bold" font-size="{size}" fill="{INK}">'
        f'{esc(title)}</text>')
    parts.append(
        f'<text x="24" y="118" font-family="Liberation Sans" '
        f'font-size="16" fill="{SLATE}">'
        f'A Comprehensive Visual Briefing of Tuesday\u2019s Key Global '
        f'Developments</text>')
    parts.append(f'<line x1="24" y1="128" x2="1000" y2="128" '
                 f'stroke="{INK}" stroke-width="3"/>')
    parts.append(f'<line x1="24" y1="133" x2="1000" y2="133" '
                 f'stroke="{INK}" stroke-width="1"/>')

    # ---- row 1: three hero banners
    hero_y, hero_h, hero_w = 144, 208, 318
    for i, (num, tag, color, head, body, scene_fn) in enumerate(HEROES):
        x = 24 + i * (hero_w + 11)
        parts.append(hero_card(x, hero_y, hero_w, hero_h, num, tag,
                               color, head, body, scene_fn, warnings))

    # ---- rows 2-4: dense 12-story grid, 4 x 3
    grid_y0, card_w, card_h = 362, 236.5, 140
    for i, (num, tag, color, head, body) in enumerate(STORIES):
        row, col = divmod(i, 4)
        x = 24 + col * (card_w + 10)
        y = grid_y0 + row * (card_h + 10)
        parts.append(grid_card(x, y, card_w, card_h, num, tag, color,
                               head, body, warnings))

    # ---- bottom row: world map widget + key themes panel
    parts.append(map_widget_svg(24, 812, 390, 192))
    parts.append(key_themes_panel(424, 812, 576, 192))

    parts.append('</svg>')
    svg = "\n".join(parts)
    (HERE / "entry.svg").write_text(svg, encoding="utf-8")

    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(HERE / "entry.png"),
                     output_width=W, output_height=H)
    img = Image.open(HERE / "entry.png")
    assert img.size == (W, H), f"bad size {img.size}"
    img.save(HERE / "entry.png", optimize=True)
    size_bytes = os.path.getsize(HERE / "entry.png")
    print(f"base render: {size_bytes} bytes")
    if size_bytes > 240 * 1024:
        # Lossless first: Zopfli re-compresses the same pixels.
        zsize = zopfli_pass(HERE / "entry.png")
        if zsize is not None:
            size_bytes = zsize
            print(f"zopfli render: {size_bytes} bytes")
    if size_bytes > 240 * 1024:
        # Deterministic palette pass: flat vector art quantizes
        # cleanly to 256 colours; re-save and re-check.
        img = img.convert("P", palette=Image.ADAPTIVE, colors=256)
        img.save(HERE / "entry.png", optimize=True)
        size_bytes = os.path.getsize(HERE / "entry.png")
        print(f"palette 256 render: {size_bytes} bytes")
    if size_bytes > 240 * 1024:
        img = Image.open(HERE / "entry.png").convert("RGB")
        img = img.convert("P", palette=Image.ADAPTIVE, colors=128)
        img.save(HERE / "entry.png", optimize=True)
        size_bytes = os.path.getsize(HERE / "entry.png")
        print(f"palette 128 render: {size_bytes} bytes")
    final = Image.open(HERE / "entry.png")
    assert final.size == (W, H), f"bad size {final.size}"
    sha = hashlib.sha256((HERE / "entry.png").read_bytes()).hexdigest()
    print(f"wrote entry.png {final.size} {size_bytes} bytes "
          f"sha256 {sha}")
    print(f"masthead title size {size}px")
    if size_bytes >= 1024 * 1024:
        print(f"WARNING: entry.png {size_bytes} bytes >= 1 MiB")
    for warn in warnings:
        print("WARNING:", warn)
    if warnings:
        raise SystemExit(f"{len(warnings)} layout warnings — fix them")


if __name__ == "__main__":
    main()
