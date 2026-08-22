---
name: eve-glyph-rebuild-catalogue
description: Rebuild the EVE Frontier Glyph Explorer catalogue, sequences, atlas, JavaScript data wrappers, and frame-evidence manifests from ArchiveInvest tags and provisional analysis outputs. Use after source, dictionary, occurrence, phrase, or classification changes.
license: MIT
---

# Rebuild the glyph catalogue

When working in the Glyph Explorer repository, read the root `AGENTS.md`. Generated artifacts form one release unit; do not update only the file that is convenient.

The committed pipeline requires Python, Pillow, NumPy, FFmpeg, the ArchiveInvest corpus, and the private source-video directory. Read `pipeline/README.md` for the complete fresh-fork example.

## Required inputs

Confirm these external inputs are available before rebuilding:

- ArchiveInvest `PatternCSVs/glyph_dictionary.csv`;
- all included `PatternCSVs/*_patterns.csv` files;
- ArchiveInvest `broadcasts.csv` and `phrases.csv`;
- the exact provisional capture files declared in `pipeline/corpus.json`;
- every exact source video named by evidence records;
- explicit source-file overrides, including `E6C2-1K -> E6C2-1K zoomed.mp4`.

Run the non-mutating audit first:

```powershell
python pipeline\inventory_sources.py --verify --downloaded-dir <source-videos> --archive-video-dir <ArchiveInvest>\Videos
python pipeline\run_pipeline.py --archive-invest <ArchiveInvest> --video-dir <source-videos> --check-inputs
```

If a required raw input is unavailable or fails SHA-256 verification, stop rather than reconstructing generated rows by hand. Regenerate the manifest only after confirming that a file change is intentional and recording its provenance.

## Build order

Use the supported entry point; it performs the stages in the required order:

```powershell
python pipeline\run_pipeline.py --archive-invest <ArchiveInvest> --video-dir <source-videos>
```

It calls `analyze_sources.py`, `build_site.py`, and `scripts/validate_repository.py`. Use `--skip-analysis` only to reuse an existing reviewed `.pipeline-work/analysis/glyph_sequences.csv` plus its sampled frame images.

Use the Python interpreter that has Pillow and NumPy. Use the same FFmpeg major/version for a release when practical so regenerated JPEGs do not create unrelated binary diffs.

## Merge semantics

- Build canonical glyphs from the ArchiveInvest dictionary.
- Convert manual `cells` to an 81-bit row-major fingerprint and assign exact dictionary IDs where possible.
- Keep nearest manual assignments visibly labelled and counted.
- Add automatic records as provisional. When a logical broadcast already has manual tags, give the automatic capture a distinct `recording` label.
- Apply contextual overrides only through a visible mapping in the generator; include the original observed fingerprint and distance.
- Sort occurrences by `recording`, then `ordinal`.
- Derive sequence, frequency, transition, repeated-block, family, symmetry, and corpus statistics from the complete occurrence set.
- Use `recording`, not `broadcast`, when looking up a specific sequence. `broadcast` can intentionally collide across captures.

## Generated artifact contract

Regenerate together:

- `data/catalogue.json`
- `data/catalogue.js`
- `data/glyph_catalogue.csv`
- `data/glyph_occurrences.csv`
- `data/sequences.csv`
- `assets/glyph-atlas.png`
- `data/evidence.json`
- `data/evidence.js`
- `data/evidence_manifest.csv`
- all affected `evidence/**/*.jpg`
- `data/source_integrity.json` and `.csv` whenever locally available source media changes
- `data/disputed_cell_audit.json` and `.csv` plus `evidence/audits/*.jpg` whenever a disputed-cell audit changes

`catalogue.js` must contain the exact JSON object from `catalogue.json`, assigned to `window.GLYPH_DATA`. `evidence.js` follows the same rule with `window.GLYPH_EVIDENCE`.

Do not delete old evidence directories until the new occurrence set and intended removal scope are known. If removals are required, resolve the exact recording-specific directories and review the Git diff before deleting.

## Review the diff

Before committing:

1. Compare corpus counts with the previous release and explain every delta.
2. Confirm manual/provisional totals.
3. Review any new canonical IDs, unmatched manual rows, contextual overrides, and Hamming-distance changes.
4. Confirm sequence lengths equal occurrence counts grouped by `recording`.
5. Check that only intended evidence directories changed.
6. View representative regenerated atlas and evidence images.

## Validate

```powershell
python scripts/validate_repository.py
node --check assets/app.js
node --check data/catalogue.js
node --check data/evidence.js
```

The validator proves cross-file structure and coverage, not that the selected source frames contain glyphs. Use the evidence-audit skill for semantic frame verification.
