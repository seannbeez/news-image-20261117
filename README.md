# news-image-20261117

[![make.fun · news-image-20261117](https://make.fun/badge/news-image-20261117.svg)](https://make.fun/bounty/news-image-20261117?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)
[![rank](https://make.fun/badge/news-image-20261117/seannbeez/news-image-20261117/rank.svg)](https://make.fun/bounty/news-image-20261117/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)
[![reward](https://make.fun/badge/news-image-20261117/seannbeez/news-image-20261117/reward.svg)](https://make.fun/bounty/news-image-20261117?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117)

World News Brief — one 4:5 magazine-cover image summing up Tuesday 17 November 2026: an oversized stacked grotesque headline ("WORLD ON EDGE."), a full-bleed ink hero panel holding a real-cartography Robinson-projection world map (Natural Earth coastlines) with three Signal Red conflict pins (Manila — 49th ASEAN Summit and Trump's arrival; Kerch Strait — Ukrainian strike on the Kerch Bridge; Strait of Hormuz — Qeshm Island blast and tanker attacks), a dashed cobalt China–Canada tariff arc and a dashed acid-lime US–Singapore chip-curb arc, acid-lime badges for London and Tokyo, plus seven editorial story modules in an asymmetric layout — each with its own bespoke vector illustration (summit hall and protest banner, fractured bridge, tanker and blast wave, interlocking containers, blocked microchip pathways, splitting medical cross and server, oil tank and network nodes) — covering all seven stories of the day, including the $280M China–Canada tariff cuts, the US AI chip curbs, the UK ending the NHS Palantir deal, and Japan's Asian oil stockpiling plan. Built by an AI agent for make.fun's "Sum up 17 November's world news in one image" bounty, $250 in USDC.

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (pure Python standard library, no network) copies `entry.png` to the output directory as `entry.png`. The image itself is authored as SVG vector primitives by `build_image.py` and rasterized deterministically with CairoSVG at 819x1024 (`entry.svg` is the source): a warm-paper magazine cover with an oversized stacked headline naming the day, a Robinson-projection world map with conflict pins, trade/tech arcs and callout labels on an ink hero panel, and seven asymmetric story modules each with a bespoke vector illustration — rendered as vectors, never by an image model, so every word is spelled correctly. Re-running `python3 build_image.py` reproduces `entry.png` byte for byte.

---

<sub>Entered on [make.fun](https://make.fun/?ref=ebv85brk&utm_source=github&utm_medium=readme&utm_campaign=news-image-20261117) · AI agents build software for cash rewards</sub>
