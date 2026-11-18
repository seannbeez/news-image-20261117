"""Prepare the map data for the World News Brief v3 image.

Reads the Natural Earth countries GeoJSON (data/countries.geo.json,
minified to one line from the downloaded file so the repository stays
self-contained), then derives a simplified coastline set
(data/coast.json, also one line): Douglas-Peucker simplification at
0.02 degrees, coordinates rounded to 0.01 degrees. At the map's scale
(~2 px per degree) that is sub-pixel, so nothing visible is lost,
while the file stays small. Antarctica is dropped: it is outside the
map window (the whole world, lon -180..180, lat -60..90).

Run from the repository root:  python3 tools/prep_coast.py
Both output files are deterministic: same input, same bytes.
"""

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = Path("/tmp/countries.geo.json")
GEO_OUT = HERE / "data" / "countries.geo.json"
COAST_OUT = HERE / "data" / "coast.json"

TOLERANCE = 0.02  # degrees; ~0.05 px at the map's scale


def _perp_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify_ring(ring, tol):
    """Douglas-Peucker on a closed ring (first point == last point)."""
    pts = [tuple(p) for p in ring]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        worst, worst_i = -1.0, -1
        for i in range(a + 1, b):
            dist = _perp_dist(pts[i][0], pts[i][1], ax, ay, bx, by)
            if dist > worst:
                worst, worst_i = dist, i
        if worst > tol:
            keep[worst_i] = True
            stack.append((a, worst_i))
            stack.append((worst_i, b))
    out = [pts[i] for i, kept in enumerate(keep) if kept]
    return out


def simplify_and_quantize(ring):
    pts = simplify_ring(ring, TOLERANCE)
    out = []
    for lon, lat in pts:
        q = (round(lon, 2), round(lat, 2))
        if not out or out[-1] != q:
            out.append(q)
    return out


def in_window(lon, lat):
    return -180.0 <= lon <= 180.0 and -60.0 <= lat <= 90.0


def main():
    raw = json.loads(SRC.read_text())
    feats = raw["features"]
    print(f"loaded {len(feats)} features from {SRC}")

    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEO_OUT.write_text(json.dumps(raw, separators=(",", ":")))
    print(f"wrote {GEO_OUT} ({GEO_OUT.stat().st_size} bytes, 1 line)")

    polys = []
    points_before = 0
    for feat in feats:
        name = (feat.get("properties") or {}).get("name", "")
        if name == "Antarctica":
            continue
        geom = feat["geometry"]
        rings = []
        if geom["type"] == "Polygon":
            rings = geom["coordinates"]
        elif geom["type"] == "MultiPolygon":
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        for ring in rings:
            points_before += len(ring)
            simple = simplify_and_quantize(ring)
            if len(simple) < 3:
                continue
            # Keep the ring only if some of it can appear on the map.
            if not any(in_window(lon, lat) for lon, lat in simple):
                continue
            polys.append(simple)

    points_after = sum(len(p) for p in polys)
    COAST_OUT.write_text(
        json.dumps({"polys": polys}, separators=(",", ":"))
    )
    print(f"kept {len(polys)} rings, {points_before} -> {points_after} points")
    print(f"wrote {COAST_OUT} ({COAST_OUT.stat().st_size} bytes, 1 line)")

    # Verification: every story region must still have coastline left.
    checks = {
        "Philippines (115..130E, 5..20N)": (115, 130, 5, 20),
        "Japan (129..146E, 30..46N)": (129, 146, 30, 46),
        "UK (-6..2E, 49..59N)": (-6, 2, 49, 59),
        "Kerch (32..40E, 44..47N)": (32, 40, 44, 47),
        "Hormuz (48..58E, 24..31N)": (48, 58, 24, 31),
        "Taiwan (119..122E, 22..25N)": (119, 122, 22, 25),
    }
    for label, (lo0, lo1, la0, la1) in checks.items():
        n = sum(
            1
            for poly in polys
            for lon, lat in poly
            if lo0 <= lon <= lo1 and la0 <= lat <= la1
        )
        print(f"  {label}: {n} points")
        assert n > 0, f"no coastline left in {label}"


if __name__ == "__main__":
    main()
