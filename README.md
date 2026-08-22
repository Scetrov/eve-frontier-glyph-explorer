# Frontier Archive Glyph Explorer

An unofficial, static explorer for the 9×9 glyph sequences found in EVE Frontier Archive broadcasts.

Source, release history, and issue reporting live at [Scetrov/eve-frontier-glyph-explorer](https://github.com/Scetrov/eve-frontier-glyph-explorer). The explorer supplies prefilled GitHub Issue links for selected glyphs, individual frame evidence, and reviewed cells; use them to preserve the exact context needed to reproduce a concern.

The published [Cycle reference](cycles.html) records UTC start/end dates for Phases 1–5 and Era 5–6 cycles. Its `data/cycles.json` source aligns Era 6 boundaries to confirmed whole-hour noon UTC cutovers while retaining the supplied duplicate E6C6 short name for review.

## Publish with GitHub Pages

1. Create a new GitHub repository.
2. Upload everything in this folder to the repository root.
3. Open **Settings → Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Select the `main` branch and `/ (root)`, then save.

No build step, package manager, server, API key, or database is required. The site uses relative paths and works under a project repository URL such as `https://username.github.io/repository-name/`.

## Data files

- `data/catalogue.js` powers the explorer without a network request.
- `data/catalogue.json` is the full machine-readable dataset.
- `data/evidence.js` and `data/evidence_manifest.csv` map every matched occurrence to its actual source frame.
- `data/source_integrity.json` publishes SHA-256 and FFprobe metadata for every available raw source without redistributing the media.
- `data/disputed_cell_audit.json` records the registered multi-frame review of glyphs #130 and #140.
- `data/cycles.json` is the reviewed UTC reference for phases and cycles; `data/cycles.js` lets the standalone reference page work without fetch.
- `evidence/` contains one 480×480 audit image for each of the 768 occurrence records.
- The CSV files are downloadable from the Method section.

Every evidence record names its source video, exact source-frame number, timestamp, matching basis, and canonical/observed Hamming distance. The 181 automatically extracted local-video occurrences are marked provisional. Canonical dictionary patterns and manual tags are derived from [QZRChedders/ArchiveInvest](https://github.com/QZRChedders/ArchiveInvest).

Two singleton carrier-edge marks were corrected after seven-frame median review: `(2,6)` in glyph #130 was checked in two independently hashed E6C4-17 variants, and `(5,2)` in glyph #140 was checked in E6C4-35. The explorer retains stable glyph IDs and publishes the audit inputs/results.

Frame numbers are relative to the exact filename in each evidence record. In particular, the `E6C2-1K` pattern CSV was tagged against `E6C2-1K zoomed.mp4`, not the longer plain `E6C2-1K.mp4` source.

EVE Frontier and associated marks belong to their respective owners. This community research tool is not affiliated with or endorsed by the game's creators.

## Maintaining the project

Start with [AGENTS.md](AGENTS.md) for the repository architecture, data contracts, build order, validation gates, provenance rules, and release process. Reusable agent workflows live in [`.agents/skills/`](.agents/skills/) and follow the [Agent Skills](https://agentskills.io/) format used by [skills.sh](https://skills.sh/).

The complete raw-video-to-site workflow is included under [`pipeline/`](pipeline/README.md). A fork can supply the uncommitted source videos, check exact input resolution, and rebuild all catalogue, codex, occurrence, and frame-evidence artifacts with one command:

```powershell
python -m pip install -r pipeline\requirements.txt
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos
```

Use `--check-inputs` first to validate the source layout without modifying generated files. The [pipeline guide](pipeline/README.md) includes exact filenames, a fresh-fork setup, FFmpeg examples, and worked manual/provisional source additions.

Run the repository validator before every data or evidence release:

```powershell
python scripts/validate_repository.py
node --check assets/app.js
node --check assets/release.js
node --check assets/cycles.js
node --check data/catalogue.js
node --check data/evidence.js
```
