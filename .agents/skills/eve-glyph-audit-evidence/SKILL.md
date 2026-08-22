---
name: eve-glyph-audit-evidence
description: Audit or correct EVE Frontier glyph evidence when a frame looks ordinary, a mark appears inside the carrier diamond, a match seems wrong, or source variants may be misaligned. Use for frame-reference disputes and visual catalogue verification.
license: MIT
---

# Audit glyph frame evidence

When working in the Glyph Explorer repository, read the root `AGENTS.md`. Diagnose before changing an assignment. A wrong evidence image can result from a correct glyph tag paired with the wrong video variant.

This workflow requires the exact source videos plus FFmpeg/FFprobe. Use image viewing support for the visual checks.

## Trace the record

Locate the occurrence in all three datasets:

```powershell
rg -n "<recording>|<frame>" data/glyph_occurrences.csv data/evidence_manifest.csv data/evidence.json
```

Record the matched glyph ID, recording, broadcast, ordinal, frame, timestamp, source class, assignment basis, observed fingerprint, and the manifest's exact `source_video`.

## Verify the source file

1. Resolve the exact manifest filename. Do not select a file by broadcast-prefix glob if multiple variants exist.
2. Probe frame rate, duration, dimensions, and decoded frame count with FFprobe.
3. Compare the metadata with the file used to create the pattern CSV or provisional row.
4. List alternate files such as original, close-up, zoomed, crop, transcode, MOV, MP4, and WebM variants.

Frame indices are zero-based FFmpeg decoded-frame indices. Extract the disputed frame without timestamp seeking:

```powershell
ffmpeg -hide_banner -loglevel error -i "<exact-video-path>" `
  -vf "select=eq(n\,<frame>)" -fps_mode vfr -frames:v 1 "audit_f<frame>.png"
```

Extract a small neighbourhood and the same index from every plausible variant. Timestamp seeking alone is insufficient for a frame-identity audit.

## Classify the failure

- **Wrong source variant:** the indexed frame contains a glyph in another derived file. Correct `source_video`, regenerate the whole recording's evidence set, and document the override.
- **Off-by-one/index convention:** adjacent frame contains the intended glyph. Confirm whether the tagger and extractor use zero-based decoding; correct the generating data rather than only renaming an image.
- **Transition frame:** the frame mixes two states. Select a settled frame only if the source tag is also corrected and the reason is documented.
- **Incorrect tag:** the exact frame is correct but its observed cells do not match the stored fingerprint. Preserve the image, retag upstream, rebuild, and keep the discrepancy visible until resolved.
- **Carrier/diamond ambiguity:** inspect the unmasked source at full resolution. Do not delete a mark solely because its position is normally carrier territory. Record whether the canonical fingerprint excludes it and flag the occurrence for review.
- **Compression or crop failure:** obtain a higher-quality or correctly aligned source. Keep variants separate until equivalence is demonstrated.

## Correct safely

Fix the earliest authoritative layer:

1. source-file override or source registry;
2. manual pattern CSV or provisional analysis row;
3. catalogue rebuild;
4. evidence regeneration;
5. static site data wrappers.

Do not patch only the JPEG or only the manifest. Regenerate every occurrence for the affected recording when the source file changes. This prevents a mixture of timelines within one sequence.

## Validate the correction

- View the disputed frame after regeneration.
- View the first, middle, and last frame of the affected recording.
- Confirm all of that recording's manifest rows name one intended exact source, unless a documented per-occurrence exception is genuinely required.
- Confirm all other recordings' evidence files are unchanged.
- Run `python scripts/validate_repository.py` and JavaScript syntax checks.
- After deployment, download the live image with a cache-busting query and compare its SHA-256 with the committed file.

Report the root cause, old and corrected source filenames, number of affected occurrences, frame-index convention, validation result, and any cells still requiring human judgement.
