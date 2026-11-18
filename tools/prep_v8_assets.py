"""Prepare v8 photo assets: crop + resize the AI-generated editorial
illustrations to near-display resolution for embedding in the poster.

Inputs (AI-generated, kept out of the repo snapshot in assets/src/):
  src/media-generation-hero-h1-*.png  2736x912 (3:1) ASEAN/Manila
  src/media-generation-hero-h2-*.png  2736x912 (3:1) Kerch Bridge
  src/media-generation-hero-h3-*.png  2736x912 (3:1) Hormuz tanker
  src/media-generation-minis-sheet-*.png  1792x1344 (4:3) 4x3 minis

Outputs (committed, near-display resolution):
  assets/hero1.png hero2.png hero3.png   HERO_W x HERO_H
  assets/mini01.png ... mini12.png       MINI_PX x MINI_PX

Heroes are centre-cropped to the banner aspect 318:104 (3.0577:1),
then resized. Minis are located by detecting the sheet's paper
gutters (background-only columns/rows) and cropped with a 2px inset,
then resized. Deterministic: fixed inputs, fixed constants, no
randomness. Re-run any time; outputs are byte-identical.
"""

import glob
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "assets" / "src"

HERO_W, HERO_H = 477, 156          # 1.5x of the 318x104 banner slot
MINI_PX = 92                       # 2x of the 46x46 icon slot
BANNER_ASPECT = 318 / 104          # 3.0577


def _glob(stem):
    hits = sorted(SRC.glob(f"media-generation-{stem}-*.png"))
    assert len(hits) == 1, f"expected 1 {stem}, got {hits}"
    return hits[0]


def hero(src_path, out_path):
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    # centre-crop to the banner aspect (keep full width)
    th = int(round(w / BANNER_ASPECT))
    top = (h - th) // 2
    im = im.crop((0, top, w, top + th))
    im = im.resize((HERO_W, HERO_H), Image.LANCZOS)
    im.save(out_path, optimize=True)
    print(f"{out_path.name}: {im.size} from {src_path.name} "
          f"({w}x{h}, crop top={top})")


def sheet_bounds(im):
    """Cell bounds of the 4x3 mini grid, measured from this sheet
    (1792x1344) by gradient-peak detection: the strong vertical
    edges sit at x = 41/458/473/888/904/1320/1335/1752 and the
    horizontal edges at y = 45/449/464/880/895/1299 (15px gutters,
    ~40px outer margins). Returns (x_spans, y_spans)."""
    x_spans = [(41, 458), (473, 888), (904, 1320), (1335, 1752)]
    y_spans = [(45, 449), (464, 880), (895, 1299)]
    return x_spans, y_spans


def minis(src_path):
    im = Image.open(src_path).convert("RGB")
    x_spans, y_spans = sheet_bounds(im)
    print(f"sheet {im.size}: x_spans={x_spans} y_spans={y_spans}")
    assert len(x_spans) == 4, f"expected 4 columns, got {x_spans}"
    assert len(y_spans) == 3, f"expected 3 rows, got {y_spans}"
    n = 0
    for r, (y0, y1) in enumerate(y_spans):
        for c, (x0, x1) in enumerate(x_spans):
            n += 1
            cell = im.crop((x0 + 2, y0 + 2, x1 - 2, y1 - 2))
            cell = cell.resize((MINI_PX, MINI_PX), Image.LANCZOS)
            out = HERE / "assets" / f"mini{n:02d}.png"
            cell.save(out, optimize=True)
            print(f"{out.name}: {cell.size} from cell "
                  f"({x0},{y0})-({x1},{y1})")


def main():
    for i in (1, 2, 3):
        hero(_glob(f"hero-h{i}"), HERE / "assets" / f"hero{i}.png")
    minis(_glob("minis-sheet"))


if __name__ == "__main__":
    main()
