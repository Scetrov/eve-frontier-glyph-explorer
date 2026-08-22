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

1. Run `pipeline/inventory_sources.py --verify` against `data/source_integrity.json`. Stop the audit on any missing, size-mismatched, or SHA-256-mismatched input.
2. Resolve the exact manifest filename and record its SHA-256 in the audit result. Do not select a file by broadcast-prefix glob if multiple variants exist.
3. Probe frame rate, duration, dimensions, and decoded frame count with FFprobe.
4. Compare the metadata with the file used to create the pattern CSV or provisional row.
5. List alternate files such as original, close-up, zoomed, crop, transcode, MOV, MP4, and WebM variants. Hash every variant; matching names or visual similarity do not establish identity.

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

For a disputed cell, independently register the 9×9 lattice for each source variant and use multiple settled frames. Publish the sampled frame numbers, per-source SHA-256, registration geometry, a median image, quantitative score, threshold, and verdict. Keep stable glyph IDs when correcting a false cell unless an upstream ID migration is explicitly coordinated.

## Optional learned-registration proposal

When classical lattice fitting cannot cover crop or zoom variation, use `pipeline/vision_registration_spike.py` only as a proposal generator. Use `pipeline/hybrid_registration_spike.py` when the audit needs direct-versus-temporal consensus plus independent lattice and diamond support. Install the isolated `pipeline/requirements-vision-spike.txt`, verify the checkpoint SHA-256 declared by `pipeline/vision_spike_config.json`, and run either experiment only after the normal raw-source integrity check passes.

Do not treat LoFTR match count, inlier ratio, or homography reprojection error as proof. E6C4-35 frame 340 retains a low match reprojection error despite materially incorrect corners. Also verify the reference annotation: the hybrid diamond check found that the first E6C4-35 frame 57 label was one pitch high. Keep model coordinates experimental until independent grid/diamond fit, adjacent-frame temporal agreement, and human review all support them. Never train or select registration from corpus fingerprints.

## Validate the correction

- View the disputed frame after regeneration.
- View the first, middle, and last frame of the affected recording.
- Confirm all of that recording's manifest rows name one intended exact source, unless a documented per-occurrence exception is genuinely required.
- Confirm all other recordings' evidence files are unchanged.
- Re-run the source integrity verifier, `python scripts/validate_repository.py`, and JavaScript syntax checks.
- After deployment, download the live image with a cache-busting query and compare its SHA-256 with the committed file.

Report the root cause, old and corrected source filenames, number of affected occurrences, frame-index convention, validation result, and any cells still requiring human judgement.
