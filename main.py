"""World News Brief v2 — 17 November 2026 (make.fun news-image-20261117).

The entry is a single pre-drawn executive-briefing image, entry.png,
rendered deterministically with Pillow by build_image.py: a 1024x576
(16:9) warm-ivory broadsheet with a serif masthead naming Tuesday
17 November 2026, a simplified world map on the left with three
numbered flashpoint pins (Manila, Kerch Strait, Strait of Hormuz),
and five data cards on the right covering all six verified stories
of that day (ASEAN summit in Manila, the Kerch Bridge strike, the
Qeshm Island blasts and Hormuz tanker attacks, the China–Canada
$280M tariff cuts, the NHS Palantir contract ending in 2029, and
Japan's Asian oil stockpiling proposal).

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
