# Reproducible pipeline

This directory contains the complete path from raw, locally held source videos to the static catalogue and frame-evidence explorer. The repository does not redistribute source videos; a fork supplies those inputs locally and can reproduce every committed derivative artifact.

## What the pipeline does

`run_pipeline.py` performs four ordered stages:

1. validates every manual and provisional input and resolves each frame index to one exact filename;
2. uses FFmpeg to extract configured settled frames and classify their 9×9 payloads;
3. merges ArchiveInvest manual tags with provisional reads, derives statistics/sequences, and renders the atlas;
4. extracts one 480×480 evidence image per occurrence and runs the repository validator.

Manual ArchiveInvest tags remain canonical corpus evidence. Automatically read captures remain explicitly provisional. Contextual corrections and exact-file overrides are visible in [`corpus.json`](corpus.json). Automatic evidence retains detector-ring geometry. Manual tags have no published detector coordinates, so their QA overlays remain unavailable until a source-frame analysis records independently reviewable geometry; never infer it from the final JPEG.

`data/source_integrity.json` publishes the SHA-256 and media identity of every locally available source without exposing local paths or redistributing raw media. Analysis must start with integrity verification.

## Prerequisites

- Python 3.11 or newer;
- FFmpeg available on `PATH`, or an explicit `--ffmpeg` path;
- a clone of [QZRChedders/ArchiveInvest](https://github.com/QZRChedders/ArchiveInvest) including its `Videos/` directory;
- the eleven additional source captures named in `corpus.json`, held in one local directory.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r pipeline\requirements.txt
git clone https://github.com/QZRChedders/ArchiveInvest ..\ArchiveInvest
```

Place the additional captures in `..\source-videos\` with these exact names:

```text
E6C4-2T.webm   E6C4-30.webm   E6C5-13.mp4   E6C5-2J.webm
E6C5-3L.webm   E6C6-1.webm    E6C6-11.webm  E6C6-1R.mov
E6C6-21.mov    E6C6-D.mov     E6C6-N.webm
```

## Check inputs without changing generated files

```powershell
python pipeline\inventory_sources.py `
  --downloaded-dir ..\source-videos `
  --archive-video-dir ..\ArchiveInvest\Videos
python pipeline\inventory_sources.py --verify `
  --downloaded-dir ..\source-videos `
  --archive-video-dir ..\ArchiveInvest\Videos
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos `
  --check-inputs
```

The command fails on a missing or ambiguous source. In particular, `E6C2-1K_patterns.csv` must resolve to `ArchiveInvest\Videos\E6C2-1K zoomed.mp4`; its indices do not describe `E6C2-1K.mp4`.

## Full end-to-end rebuild

```powershell
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos
```

If FFmpeg is not on `PATH`:

```powershell
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos `
  --ffmpeg C:\tools\ffmpeg\bin\ffmpeg.exe
```

Analysis intermediates go to `.pipeline-work/analysis/`. A later catalogue/evidence-only rebuild can reuse them:

```powershell
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos `
  --skip-analysis
```

The final stage regenerates these as one release unit:

```text
data/catalogue.json          data/catalogue.js
data/glyph_catalogue.csv     data/glyph_occurrences.csv
data/sequences.csv           assets/glyph-atlas.png
data/evidence.json           data/evidence.js
data/evidence_manifest.csv   evidence/**/*.jpg
data/source_integrity.json   data/source_integrity.csv
data/disputed_cell_audit.json data/disputed_cell_audit.csv
```

For the current corpus, a successful build reports 146 canonical glyphs, 835 occurrences, 32 recording records, 53 used payload positions, and 835 occurrence evidence images. Treat a count change as a review trigger, not automatically as an error.

## Reproduce the disputed-cell audit

After the integrity verifier passes:

```powershell
python pipeline\audit_disputed_cells.py `
  --downloaded-dir ..\source-videos `
  --archive-video-dir ..\ArchiveInvest\Videos
```

The audit independently registers each source lattice, takes a pixelwise median over seven settled frames, scores the central aperture, and publishes the exact frame list, source SHA-256, geometry, score, and median image. It currently resolves `(2,6)` in glyph #130 and `(5,2)` in glyph #140 as carrier/inactive. Under the old empirical 26-cell hypothesis they are unused payload candidates; under the symmetric 28-cell hypothesis they are excluded. After correction both hypotheses produce the same 146 IDs, but the symmetric model cleanly explains all 28 unused positions.

## Produce manual-frame geometry candidates

Manual ArchiveInvest tags do not contain the detector coordinates needed for a trustworthy QA overlay. Generate a blind source-frame backfill separately; this writes `data/manual_geometry_review.json` and `.csv` with source SHA-256, decoded frame, candidate centre/pitches, fit scores, independently detected fingerprint, corpus fingerprint, Hamming distance, detector separation, and a mandatory `pending` review state:

```powershell
python pipeline\analyze_manual_geometry.py `
  --archive-invest ..\ArchiveInvest `
  --ffmpeg C:\tools\ffmpeg\bin\ffmpeg.exe
```

The detector fits and reads the image before comparing its result with the corpus fingerprint; the tag never influences geometry or classification. The script never enables an overlay. The current v1 backfill yields 4 exact and 26 distance-1/2 results from 587 manual occurrences, with a median distance of 17. This primarily demonstrates that v1 registration is not robust across crop/zoom variants; it is not evidence that the remaining corpus tags are wrong.

## Reproduce the optional LoFTR registration spike

The experimental [`vision_registration_spike.py`](vision_registration_spike.py) asks a narrower question: can pretrained LoFTR correspondences propagate reviewed grid geometry between exact frames in one recording? It does not load corpus fingerprints or glyph IDs and cannot promote an overlay. Its PyTorch/Kornia packages are intentionally separated in [`requirements-vision-spike.txt`](requirements-vision-spike.txt).

Install those packages in an isolated environment, download the checkpoint identified in [`vision_spike_config.json`](vision_spike_config.json), verify source integrity, then run:

```powershell
.\.vision-venv\Scripts\python.exe pipeline\vision_registration_spike.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos `
  --ffmpeg C:\tools\ffmpeg\bin\ffmpeg.exe `
  --checkpoint .\loftr_outdoor.ckpt
```

The runner verifies both source-video and checkpoint SHA-256 values. It writes only to `.pipeline-work/vision-spike/run/` unless `--output-dir` is supplied. Current methodology, metrics, corrections and reviewed renders are preserved in [`research/vision-registration-spike/`](../research/vision-registration-spike/README.md). E6C4-35 frame 340 proves that low homography reprojection error is not sufficient acceptance evidence, while the corrected frame 57 reference proves that geometry labels themselves require independent review.

Run the conservative hybrid follow-up with the same inputs:

```powershell
.\.vision-venv\Scripts\python.exe pipeline\hybrid_registration_spike.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos `
  --ffmpeg C:\tools\ffmpeg\bin\ffmpeg.exe `
  --checkpoint .\loftr_outdoor.ckpt
```

The hybrid compares direct registration with short-hop all-feature and carrier-only temporal chains, then requires independent lattice and—where visible—diamond support. Manual target corners are consulted only after the operational decision. The current eight-pair trial yields six review candidates, zero false-positive candidates, one conservative false rejection and one correct rejection. See [`research/hybrid-registration-spike/`](../research/hybrid-registration-spike/README.md).

## Add a provisional capture: worked example

Suppose `E6C7-AB.mov` has a visible glyph interval whose transitions begin at decoded frame 600 and end at 720, with a six-frame cadence. First establish the exact-file contract:

```powershell
ffprobe -v error -select_streams v:0 `
  -show_entries stream=codec_name,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames `
  -of default=noprint_wrappers=1 ..\source-videos\E6C7-AB.mov
Get-FileHash ..\source-videos\E6C7-AB.mov -Algorithm SHA256
ffmpeg -hide_banner -loglevel error -i ..\source-videos\E6C7-AB.mov `
  -vf "select=eq(n\,605)" -fps_mode vfr -frames:v 1 frame_000605.png
```

Then add this object to `automatic_sources` in `corpus.json`:

```json
{
  "broadcast": "E6C7-AB",
  "file": "E6C7-AB.mov",
  "first_change": 600,
  "last_change": 720,
  "last_safe": 725,
  "cadence": 6,
  "sample_offset": 5
}
```

Run the input check, then the full rebuild. Review `.pipeline-work/analysis/contact_sheets/E6C7-AB.jpg`, every classification with Hamming distance over 2, and several exact matches before publishing. Update `SOURCES.md`, `credits.html`, and the private source ledger with URL/provider, acquisition date, checksum, media properties, contributor, derivation status, and rights note.

For irregular cadence, declare exact settled frames instead:

```json
{
  "broadcast": "E6C7-AB",
  "file": "E6C7-AB.mov",
  "sample_frames": [605, 611, 618, 624]
}
```

## Add or update a manual source

Add the trusted `E6C7-AB_patterns.csv` and any dictionary change upstream in ArchiveInvest. The CSV must retain its ArchiveInvest schema and decoded-frame indices. If those indices refer to a derived or non-default video, declare the filename explicitly:

```json
"manual_source_overrides": {
  "E6C2-1K": "E6C2-1K zoomed.mp4",
  "E6C7-AB": "E6C7-AB close-up.mp4"
}
```

Never select a video merely because its prefix matches. The pipeline deliberately fails ambiguous resolution.

## Manual review and release checks

```powershell
python pipeline\inventory_sources.py --verify --downloaded-dir ..\source-videos --archive-video-dir ..\ArchiveInvest\Videos
python scripts\validate_repository.py
node --check assets\app.js
node --check data\catalogue.js
node --check data\evidence.js
git diff --stat
git diff -- data\sequences.csv data\glyph_occurrences.csv data\evidence_manifest.csv
```

Serve the root with `python -m http.server 8000` and use the Cell Activation panel to choose any `(row,column)`. It lists all matching canonical patterns and every occurrence-level source frame for manual review. A structural pass does not prove that the detector chose a semantically correct frame; review evidence against the exact named video.

## Detector boundaries

The detector centre-crops each selected frame, fits the grid, samples a ring around each cell, and historically excluded an empirical 26-cell carrier mask. The two remaining symmetric edge positions have now been independently audited as carrier cells; the site presents the resulting 28-cell mask. Evidence remains unmasked so unexpected diamond-adjacent marks can be audited. Automatically assigned IDs are nearest canonical patterns, not newly created dictionary glyphs.
