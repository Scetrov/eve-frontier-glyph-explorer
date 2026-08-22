---
name: eve-glyph-add-source
description: Add a new EVE Frontier broadcast video, manual pattern CSV, or provisional local capture to the Glyph Explorer while preserving exact file identity, frame references, provenance, and licensing boundaries. Use for new recordings, replacement media, source variants, or contributor-supplied tags.
license: MIT
---

# Add an EVE Frontier glyph source

When working in the Glyph Explorer repository, read the root `AGENTS.md` before changing data. Treat acquisition, analysis, and publication as distinct stages. Raw media normally remains outside the Git repository.

Video ingestion requires FFmpeg/FFprobe. The committed automatic-analysis pipeline also requires Python, Pillow, and NumPy. Read `pipeline/README.md` for complete commands and worked configuration examples.

## Choose the ingestion path

Use the **manual path** when a trusted per-broadcast `*_patterns.csv` exists and its cells have been visually tagged. Use the **provisional path** for a newly supplied video whose grid is classified automatically. Never relabel provisional output as manual because it resembles a known sequence.

If the logical broadcast already exists, create a distinct `recording` value such as `E6C4-2T [local capture]`; retain the shared `broadcast` label. Do not merge variants until exact file equivalence and frame alignment are proven.

## Register the exact source

Before decoding frames, record in the private source ledger:

- logical broadcast and proposed recording labels;
- exact filename, including spaces and extension;
- source URL/provider, contributor, and acquisition date;
- SHA-256 checksum;
- whether it is original, transcoded, cropped, close-up, zoomed, or otherwise derived;
- license/rights note and whether redistribution is permitted.

Then regenerate the committed integrity manifest before analysis. The manifest is the public identity contract for raw files even though the files themselves are not redistributed:

```powershell
python pipeline\inventory_sources.py --downloaded-dir <source-videos> `
  --archive-video-dir <ArchiveInvest>\Videos
python pipeline\inventory_sources.py --verify --downloaded-dir <source-videos> `
  --archive-video-dir <ArchiveInvest>\Videos
```

Never replace a file in place while retaining its old manifest entry. A changed SHA-256 is a distinct source variant and requires provenance/frame-alignment review.

If the source has an official EVE Frontier artifact API record, add or update the exact record in `data/official_artifacts.json` and its browser lookup in `data/official_artifacts.js`. Preserve the API-returned URL and `createdAt` exactly; label `createdAt` as artifact-record creation time rather than a broadcast date. Ensure the logical broadcast label makes matching sequence and evidence views link to that official artifact.

Probe the exact file:

```powershell
ffprobe -v error -select_streams v:0 `
  -show_entries stream=codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,start_time,duration,nb_frames `
  -of default=noprint_wrappers=1 "<exact-video-path>"
Get-FileHash "<exact-video-path>" -Algorithm SHA256
```

Do not assume `frame / 30` if FFprobe reports another rate. Preserve source timestamps from the tagging or detection process.

## Establish the frame-index contract

The catalogue uses FFmpeg decoded-frame indices compatible with `select=eq(n\,FRAME)`. Verify a known or candidate frame directly:

```powershell
ffmpeg -hide_banner -loglevel error -i "<exact-video-path>" `
  -vf "select=eq(n\,238)" -fps_mode vfr -frames:v 1 "frame_000238.png"
```

Check the requested frame and nearby frames. If another file with the same broadcast prefix exists, extract the same index from each variant. Record an explicit source override whenever the pattern CSV was created from a non-default variant.

## Manual ArchiveInvest path

1. Confirm the input CSV follows the ArchiveInvest pattern schema: `pattern`, `frame`, `time_s`, `n_cells`, `cells`, then `r0c0` through `r8c8`.
2. Confirm each `cells` value and the 81 `r*c*` fields describe the same row-major 9×9 pattern.
3. Confirm the accompanying `glyph_dictionary.csv` uses stable IDs and fingerprints.
4. Visually inspect at least the first, middle, last, and every unusual/diamond-adjacent tagged frame against the exact indexed file.
5. Add or update the upstream manual inputs in the private analysis workspace, not directly in the generated site CSVs.
6. Update `broadcasts.csv` and `phrases.csv` only when the track or phrase assignment is supported by the upstream research.

An unmatched manual fingerprint may be assigned to the nearest canonical glyph only if the output retains `assignment_basis: nearest manual tag` and its distance. Prefer resolving the tag upstream.

## Provisional local-capture path

1. Extract lossless or high-quality centre-square frames to a recording-specific working directory. A typical filter is:

   ```powershell
   ffmpeg -i "<exact-video-path>" `
     -vf "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2'" `
     "<working-dir>/frame_%04d.jpg"
   ```

2. Use frame-difference traces and contact sheets to find the glyph interval and cadence. Do not copy cadence offsets from another broadcast without inspection.
3. Sample settled frames, not transition frames. E6 material often holds a glyph for roughly six frames at 30 fps, but cadence jitter and one-frame corrections occur.
4. Fit the 9×9 grid per recording. Retain geometry, threshold, sampled frame, observed fingerprint, nearest dictionary ID, Hamming distance, and confidence.
5. Treat the carrier-cell exclusion mask as a detection aid, not permission to crop or retouch the evidence image.
6. Mark every resulting occurrence `provisional: true`, source it as automatic FFmpeg extraction, and keep contextual corrections explicit.
7. Produce a recording contact sheet and manually review every distance greater than 2 plus representative exact and distance-1 matches.

## Integrate and generate evidence

Register provisional captures in `pipeline/corpus.json` with either cadence fields or explicit `sample_frames`. Register non-default manual variants in `manual_source_overrides`. Then run:

```powershell
python pipeline\run_pipeline.py --archive-invest <ArchiveInvest> --video-dir <source-videos> --check-inputs
python pipeline\run_pipeline.py --archive-invest <ArchiveInvest> --video-dir <source-videos>
```

The full run builds the catalogue before evidence generation. Every occurrence must receive:

- one evidence record;
- one unique 480×480 JPEG path;
- the exact source filename;
- frame, timestamp, ordinal, assignment basis, observed/canonical fingerprints, and difference cells.

Multiple occurrence rows may share a source frame. Preserve all rows and their evidence paths.

## Update attribution

Update `SOURCES.md` and `credits.html` with the contributor/source and how it was used. Update `NOTICE.md` if the rights boundary changes. Do not claim a source dataset validated a decoding unless it actually did.

## Required checks

Run:

```powershell
python scripts/validate_repository.py
python pipeline/inventory_sources.py --verify --downloaded-dir <source-videos> --archive-video-dir <ArchiveInvest>/Videos
node --check data/catalogue.js
node --check data/evidence.js
```

Then inspect the new recording in the explorer and compare several published crops to the exact local source. Report the exact filename, affected frames, manual/provisional status, and unresolved review items.
