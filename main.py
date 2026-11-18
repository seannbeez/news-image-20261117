"""World News Brief v4 — 17 November 2026 (make.fun news-image-20261117).

The entry is a single pre-drawn portrait magazine cover, entry.png,
authored as SVG vector primitives by build_image.py and rasterized
deterministically with CairoSVG: an 819x1024 (4:5) Warm Editorial
Paper cover with an oversized stacked grotesque headline ("WORLD ON
EDGE.") naming Tuesday 17 November 2026, a full-bleed ink hero panel
holding a real-cartography Robinson-projection world map (Natural
Earth coastlines from data/coast.json, simplified from
data/countries.geo.json by tools/prep_coast.py) with three Signal Red
conflict pins, two dashed trade/tech great-circle arcs and two
acid-lime badges, and seven asymmetric story modules, each with its
own bespoke vector illustration, covering all seven verified stories
of that day (ASEAN summit in Manila, the Kerch Bridge strike, the
Qeshm Island blasts and Hormuz tanker attacks, the China–Canada
$280M tariff cuts, the US AI chip curbs, the NHS Palantir contract
ending in 2029, and Japan's Asian oil stockpiling proposal).

This program does one thing: it copies that image, byte for byte, to the
grader's output location, so both runs produce identical bytes. It uses
only the Python standard library and never touches the network.

Run it outside the grader with:
    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "entry.png"


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"missing entry image: {SOURCE}")
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "entry.png"
    shutil.copyfile(SOURCE, target)
    if target.stat().st_size != SOURCE.stat().st_size:
        raise SystemExit("copied image size differs from entry.png")


if __name__ == "__main__":
    main()
