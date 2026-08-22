# Credits and sources

## Canonical glyph research

- **George Peralta / QZRChedders** — creator and maintainer of [QZRChedders/ArchiveInvest](https://github.com/QZRChedders/ArchiveInvest), including the collected source videos, manual 9×9 pattern tags, canonical glyph dictionary, transcripts, cluster analysis, and grid-tagging interface. The repository history available during this build lists `QZRChedders <george.ej.peralta@gmail.com>` as its author.
- **Locally supplied recordings** — the eleven configured Cycle 4–6 captures contribute 248 provisional classifications. Additional locally available variants and earlier-cycle files are identity-recorded in the published SHA-256 manifest but do not silently enter the catalogue.
- **E6C4-17 source comparison** — the ArchiveInvest MP4 and independently supplied WebM were both used for the registered seven-frame audit of glyph #130. Their exact hashes and media metadata are published in `data/source_integrity.json`.
- **Official EVE Frontier artifact API snapshot** — a user-supplied snapshot of 31 published `transmission` records is preserved verbatim in [`data/official_artifacts.json`](data/official_artifacts.json). The explorer uses its artifact ID/URL mapping to link matching broadcast evidence to the official artifact. The API's `createdAt` field is explicitly treated as artifact-record creation time, not asserted as original broadcast publication time. The three new glyph-bearing downloads (`E6C5-3L.webm`, `E6C6-1.webm`, and `E6C6-N.webm`) are integrity-recorded but the raw media is not committed.

## Supporting datasets

- **Scetrov** — creator and maintainer of [Scetrov/evefrontier_datasets](https://github.com/Scetrov/evefrontier_datasets), referenced for star-system and celestial-object hypotheses. The current explorer does not claim that this dataset decodes the glyphs.
- **Cycle-date reference** — the Phase and Era/Cycle project-timeline markers in [`data/cycles.json`](data/cycles.json), plus the Pre-era development context displayed on the reference page, were supplied for this explorer. The Phase dates are not server-availability windows; the 24/7 operating model began with Founders Access / Era 5. Era 6 boundaries were aligned to confirmed whole-hour noon UTC cutovers from server-transition context.

## Official context and design reference

- [EVE Frontier official site](https://evefrontier.com/)
- [EVE Frontier official media archive](https://evefrontier.com/en/media)
- [EVE Frontier official FAQ](https://evefrontier.com/en/faq)
- EVE Frontier, its universe, broadcasts, names, artwork, and associated marks belong to their respective owners, including Fenris Creations. The Archive broadcasts appear to form an intentional puzzle; this project thanks the Fenris Creations team for creating such a fun mystery to investigate. This remains an unofficial community interpretation and research tool.

## Tools and decoding references

- [FFmpeg](https://ffmpeg.org/) — video decoding and frame extraction.
- [CyberChef](https://gchq.github.io/CyberChef/) by GCHQ — inspiration for standard binary and transform-oriented decoding tests. CyberChef code is not bundled here.
- **Vision-registration feasibility work** — the isolated research spike uses the pretrained outdoor checkpoint from [LoFTR by Jiaming Sun, Zehong Shen, Yuang Wang, Hujun Bao and Xiaowei Zhou](https://github.com/zju3dv/LoFTR), accessed through [Kornia](https://github.com/kornia/kornia), with robust homography estimation from [OpenCV](https://opencv.org/). The checkpoint is downloaded by the reproducer, verified by SHA-256, and is not committed or used by the published explorer. Experimental outputs remain separate from canonical evidence.

## Interface typography

- **Disket Mono** — a display monospaced, grid-based typeface in regular and bold weights, designed by Mariano Diez with its Cyrillic set by Denis Ignatov. Typeface provenance, download, and usage information are provided by [Rostype](https://rostype.com/disket/).

## Licensing note

The MIT licence in this repository covers only the original site code. Bundled third-party font files retain their source licensing. The site licence does not relicense EVE Frontier intellectual property, third-party repositories, source videos, or datasets.
