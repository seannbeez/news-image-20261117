"""Draw the World News Brief v8 — dense 1024x1024 broadsheet.

Deterministic SVG-first rendering via CairoSVG at 1024x1024:
masthead, three photo hero banners, a dense 12-story editorial grid
(4 x 3), a Robinson-projection world map widget with numbered pins,
and a Key Themes & Daily Numbers panel. Pillow measures text with
the same Liberation fonts CairoSVG resolves, so wrapping and fitting
are exact. No image model at build time, no network, no timestamps,
no randomness.

v8 is a hybrid-pipeline Championship upgrade of v7 (Fura's order):
the exact v7 typography, data and grid are kept byte-for-byte, but
the flat geometric SVG art is replaced by AI-generated editorial
illustrations — three painterly hero banners and twelve mini
illustrations (assets/, prepared by tools/prep_v8_assets.py),
embedded as base64 data URIs with the v7 data callout tags drawn
over them as crisp SVG. Every fact, headline and figure is v7 as
verified.

Palette: warm newsprint #FAF8F3, dark navy #14213D, slate #2B4162,
crimson #C1121F, teal #1D6F72, pale-blue ocean #E3EEF5. All 15
stories (3 heroes + 12 grid) are Tuesday 17 November 2026 news
verified against live reporting; every figure on the poster comes
from the Phase 1 verification (see the builder's report).

Output: entry.png (1024x1024 JPEG, target 215-245 KB, hard cap
1 MiB) + entry.svg (the source). The rules allow PNG or JPEG in
entry.png, told apart by first bytes; the photo art needs JPEG's
DCT compression to hit the 215-245 KB window (the same pixels as
PNG cost 479 KB). Pillow's JPEG encoder is deterministic (no
EXIF, no timestamps), so main.py still writes identical bytes on
every run. A quality ladder (78/75/72/70) picks the highest
quality at or under 245 KiB; if even q70 is over, the build FAILS
rather than crushing the JPEG — lower the embed resolution
(HERO_W / HERO_H / MINI_PX in tools/prep_v8_assets.py) instead.
"""

import base64
import hashlib
import json
import math
import os
import xml.sax.saxutils as sax
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


# ------------------------------------------------------- photo embeds (v8)
# v8 is a hybrid pipeline: the three hero banners and the twelve
# card icons are AI-generated editorial illustrations (assets/,
# prepared at near-display resolution by tools/prep_v8_assets.py),
# embedded as base64 data URIs. The data callout tags stay as crisp
# SVG on top of the photos, at the exact v7 positions. No text
# inside any generated artwork (verified visually at build time).

_photo_cache = {}


def photo_uri(name):
    """data: URI for a committed asset (cached; deterministic)."""
    if name not in _photo_cache:
        data = (HERE / "assets" / name).read_bytes()
        _photo_cache[name] = ("data:image/png;base64,"
                              + base64.b64encode(data).decode("ascii"))
    return _photo_cache[name]


# (x, y, text, fill) of each hero's data callout tag, in the
# 318x104 banner space — the exact v7 positions, drawn over the
# photo so they stay crisp and legible.
HERO_TAG = {
    1: (8, 8, "MANILA \u00b7 ~2,000 PROTESTERS", INK),
    2: (8, 6, "SPAN COLLAPSED \u00b7 2 KILLED", CRIMSON),
    3: (193, 8, "TANKER HIT \u00b7 HORMUZ", CRIMSON),
}


# ------------------------------------------------------------------- stories
# (number, tag, tag colour, headline, body copy — every fact verified
# against live 17 November 2026 reporting; see the builder's report.)
HEROES = [
    (1, "GEOPOLITICS", CRIMSON,
     "49th ASEAN Summit Opens in Manila as Trump Arrives",
     "ASEAN leaders open the 49th summit in Manila as protests greet "
     "Trump's arrival.",
     "hero1.png"),
    (2, "CONFLICT", CRIMSON,
     "Ukrainian Strike Severely Damages Kerch Bridge",
     "The strike collapses a span and halts traffic; two killed, "
     "officials say.",
     "hero2.png"),
    (3, "MIDDLE EAST", CRIMSON,
     "Qeshm Blasts & Tanker Attacks Rock Hormuz",
     "Blasts rock Qeshm Island and tankers are hit in the strait, "
     "raising fears of a wider clash.",
     "hero3.png"),
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


def hero_card(x, y, w, h, num, tag, color, head, body, photo,
              warnings):
    """Hero banner: full-width photo banner, tag pill, bold title,
    2-line summary."""
    out = []
    out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" '
               f'height="{h:.0f}" fill="{CARD}" stroke="{INK}" '
               f'stroke-width="1.5"/>')
    out.append(f'<g transform="translate({x:.0f} {y:.0f})">'
               f'<image x="0" y="0" width="318" height="104" '
               f'href="{photo_uri(photo)}"/>'
               f'{scene_tag(*HERO_TAG[num])}</g>')
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
    """Dense grid card: colour top bar, tag, 46px photo mini, bold
    2-line headline, 3-line factual summary."""
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
    out.append(f'<image x="{x + 10:.0f}" y="{y + 32:.0f}" width="46" '
               f'height="46" href="{photo_uri(f"mini{num:02d}.png")}"/>')
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
    for i, (num, tag, color, head, body, photo) in enumerate(HEROES):
        x = 24 + i * (hero_w + 11)
        parts.append(hero_card(x, hero_y, hero_w, hero_h, num, tag,
                               color, head, body, photo, warnings))

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
    print(f"base render (PNG): {os.path.getsize(HERE / 'entry.png')} bytes")
    # ---- v8 output is JPEG (allowed in entry.png by first bytes):
    # the photo art needs JPEG's DCT compression to hit the
    # 215-245 KB window. Deterministic: Pillow's JPEG encoder
    # writes identical bytes for identical input + settings.
    rgb = img.convert("RGB")
    size_bytes = None
    for quality in (78, 75, 72, 70):
        rgb.save(HERE / "entry.png", "JPEG", quality=quality,
                 subsampling=2, optimize=True)
        size_bytes = os.path.getsize(HERE / "entry.png")
        print(f"jpeg q{quality}: {size_bytes} bytes")
        if size_bytes <= 245 * 1024:
            break
    if size_bytes is None or size_bytes > 245 * 1024:
        # Never crush the JPEG further: the photo illustrations
        # would band and the text would ring. Lower the embed
        # resolution instead (HERO_W / HERO_H / MINI_PX in
        # tools/prep_v8_assets.py) and re-render.
        raise SystemExit(
            f"entry.png {size_bytes} bytes > 245 KiB at JPEG q70 — "
            f"lower the embed resolution and re-render")
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
