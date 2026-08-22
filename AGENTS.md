# AGENTS.md

This file is the operating guide for humans and coding agents maintaining the EVE Frontier Glyph Explorer. It applies to the whole repository. More specialized, executable procedures are split into skills under [`.agents/skills/`](.agents/skills/).

## Mission and limits

Maintain an auditable, static explorer for the 9×9 glyph payloads seen in EVE Frontier Archive broadcasts. Preserve evidence and provenance so that every catalogue assignment can be checked against the exact source frame that produced it.

The explorer is an unofficial research tool. Do not present a speculative decoding, alphabet, starmap correlation, or lore interpretation as established fact. Separate observation, reproducible measurement, inference, and speculation in both data and prose.

## Non-negotiable data rules

1. **A frame number belongs to a file, not merely a broadcast label.** Store and display the exact source filename alongside every frame number. Derived, cropped, close-up, zoomed, transcoded, and original videos can have different timelines.
2. **Keep manual and provisional evidence separate.** ArchiveInvest manual tags are canonical corpus inputs. Automatic FFmpeg/image classifications are provisional until manually checked.
3. **Never hide disagreement.** Retain observed fingerprints, assigned glyph IDs, Hamming distance, differing cells, assignment basis, confidence when available, and the actual frame image.
4. **Preserve duplicate occurrences.** Two catalogue rows may point to the same video frame. Each occurrence still needs its own evidence record and image path because its ordinal or matched glyph can differ.
5. **Do not infer payload from the carrier diamond.** Canonical fingerprints are row-major 9×9 payload readings. The large diamond and video texture are registration/carrier graphics in the current model. Actual evidence images must remain unmasked so unusual marks can be audited.
6. **Do not renumber canonical glyph IDs casually.** IDs come from the ArchiveInvest dictionary and are stable external references. A new observed pattern is not automatically a new canonical glyph.
7. **Do not commit raw source videos.** Commit derived 480×480 evidence crops and structured data only. Keep acquisition URLs, filenames, hashes, and attribution in the source record.
8. **Preserve third-party attribution and licensing boundaries.** The MIT license covers original site code only. It does not relicense source videos, ArchiveInvest data, EVE Frontier material, or other datasets.

### Known exact-source override

`E6C2-1K_patterns.csv` was tagged against `E6C2-1K zoomed.mp4`. Its frame numbers do not refer to the longer plain `E6C2-1K.mp4`. The validator enforces this mapping. Add any future source variants explicitly; never rely on the first filename that shares a broadcast prefix.

## Repository architecture

| Path | Role | Maintainer guidance |
| --- | --- | --- |
| `index.html` | Main explorer shell and accessible dialog markup | Keep it static and usable under a GitHub project-pages subpath. |
| `credits.html` | Human-readable credits and source context | Update whenever a new contributor, dataset, or material source is added. |
| `assets/app.js` | Filtering, rendering, glyph canvases, evidence gallery, modal behavior | Uses globals from generated `data/*.js`; no bundler is involved. |
| `assets/styles.css` | EVE Frontier-inspired visual system and responsive layout | Preserve focus states, readable contrast, and mobile evidence layouts. |
| `assets/glyph-atlas.png` | Generated overview of canonical glyphs | Regenerate after canonical catalogue changes. |
| `data/catalogue.json` | Readable canonical catalogue, statistics, sequences, and analysis | Authoritative site data representation. |
| `data/catalogue.js` | Compact browser wrapper for `catalogue.json` | Must equal `window.GLYPH_DATA=<catalogue JSON>;`. |
| `data/glyph_catalogue.csv` | Flat canonical-glyph export | Generated from the same catalogue build. |
| `data/glyph_occurrences.csv` | One row per manual or provisional occurrence | Primary join input for evidence generation. |
| `data/sequences.csv` | One row per recording sequence | `recording` distinguishes captures; `broadcast` is the logical label. |
| `data/evidence.json` | Readable occurrence-to-frame evidence records | Must cover every occurrence exactly once. |
| `data/evidence.js` | Compact browser wrapper for `evidence.json` | Must equal `window.GLYPH_EVIDENCE=<evidence JSON>;`. |
| `data/evidence_manifest.csv` | Downloadable flat evidence manifest | Must describe the exact source filename and frame. |
| `evidence/<recording-slug>/` | 480×480 JPEG audit frames | Filename form is `gNNN_fNNNNNN.jpg`. Paths are unique per occurrence. |
| `scripts/validate_repository.py` | Dependency-free structural/data validator | Run before every commit that touches data, evidence, or skills. |
| `pipeline/corpus.json` | Exact source registry, sampling intervals, overrides, and corrections | Treat filename/frame mappings as reviewed data. |
| `pipeline/run_pipeline.py` | End-to-end input check, analysis, generation, and validation | This is the supported rebuild entry point. |
| `pipeline/analyze_sources.py` | FFmpeg frame extraction and provisional 9×9 classification | Review contact sheets and high-distance reads. |
| `pipeline/build_site.py` | Catalogue derivation, atlas rendering, and occurrence evidence generation | Regenerates the full artifact contract together. |
| `pipeline/README.md` | Fresh-fork setup and worked source-addition examples | Keep commands executable when pipeline behavior changes. |
| `.agents/skills/` | Reusable skills.sh-compatible maintenance workflows | Each directory contains a valid `SKILL.md`. |
| `.github/workflows/pages.yml` | GitHub Pages deployment | Deploys the repository root on pushes to `main`. |
| `.github/dependabot.yml` | GitHub Actions updates | All version updates are grouped into one PR. |
| `SOURCES.md`, `NOTICE.md`, `LICENSE` | Provenance and licensing | Keep source claims precise and current. |

## Runtime architecture

There is no production build step, package manager, API, server, database, analytics service, or secret. GitHub Pages serves the repository as static files.

`index.html` loads `data/catalogue.js`, then `data/evidence.js`, then `assets/app.js`. The generated JavaScript files assign JSON objects to `window.GLYPH_DATA` and `window.GLYPH_EVIDENCE`. This avoids a fetch dependency when the site is opened locally while retaining JSON and CSV downloads for researchers.

All URLs in HTML, CSS, and JavaScript must remain relative so the explorer works at `/eve-frontier-glyph-explorer/` rather than only at a domain root.

## Data model and joins

### Canonical glyph

- `id`: stable ArchiveInvest glyph ID.
- `fingerprint`: exactly 81 characters containing only `0` or `1`, row-major from `(0,0)` through `(8,8)`.
- `cell_indices`: zero-based active indices corresponding to the fingerprint.
- Shape, frequency, phrase, near-neighbour, transition, and symmetry fields are derived.

### Occurrence

The stable occurrence identity is the tuple `(recording, ordinal, frame, glyph_id)`. Important fields:

- `recording`: a specific corpus record; a local duplicate uses a suffix such as `[local capture]`.
- `broadcast`: logical broadcast label shared by variants.
- `ordinal`: glyph order within the recording, starting at 1.
- `frame`: FFmpeg decoded-frame index used by the source analysis.
- `time_s`: recorded timestamp; retain it rather than recomputing unless the source is reindexed.
- `source`, `provisional`, `assignment_basis`, `confidence`: provenance and status.
- `observed_fingerprint`, `hamming_distance`: what was actually read and how it relates to the assignment.

### Evidence

Every occurrence has exactly one evidence record. It repeats the occurrence identity and adds:

- exact `source_video` filename;
- `reported_hamming` and independently calculated `assigned_hamming`;
- `difference_cells` in `(row,column)` form;
- a unique relative `image` path;
- canonical and observed fingerprints.

The image is an audit artifact, not the source of truth for the structured fingerprint. If the image and tag disagree, flag the record for review; do not edit the image to resemble the tag.

## End-to-end corpus build

The generator code is committed under `pipeline/`; only raw media and transient analysis outputs remain external because of size and third-party rights. A fresh fork can reproduce all derivative site artifacts after supplying those inputs.

The supported pipeline stages are:

1. `pipeline/run_pipeline.py` validates ArchiveInvest inputs and every exact source filename declared by `pipeline/corpus.json`.
2. `pipeline/analyze_sources.py` extracts configured settled frames, fits the 9×9 grid, and retains provisional fingerprints, nearest IDs, distances, confidence, contact sheets, and geometry.
3. `pipeline/build_site.py` combines manual and provisional rows and derives catalogue, sequence, transition, repeated-block, near-twin, symmetry, and corpus data.
4. The same builder creates the glyph atlas and one unmasked evidence crop per occurrence from its exact source file.
5. JSON, JavaScript, and CSV outputs are written from the same in-memory records, then `scripts/validate_repository.py` verifies their joins and filesystem coverage.

Fresh-fork setup, exact commands, expected current counts, and worked source additions are in `pipeline/README.md`. The standard invocation is:

```powershell
python pipeline\run_pipeline.py `
  --archive-invest ..\ArchiveInvest `
  --video-dir ..\source-videos
```

Use `--check-inputs` before a first rebuild and `--skip-analysis` only when `.pipeline-work/analysis/` already contains a reviewed detector run. Do not fabricate a rebuild by hand-editing generated files.

## Common workflows

Use the focused skill matching the request:

- [Add or replace a source](.agents/skills/eve-glyph-add-source/SKILL.md): acquisition, identity, frame extraction, tagging, and provenance.
- [Rebuild catalogue artifacts](.agents/skills/eve-glyph-rebuild-catalogue/SKILL.md): ordered regeneration and generated-file contracts.
- [Audit frame evidence](.agents/skills/eve-glyph-audit-evidence/SKILL.md): investigate wrong frames, video variants, glyph disagreements, and diamond anomalies.
- [Maintain and publish the site](.agents/skills/eve-glyph-publish-site/SKILL.md): safe static edits, checks, GitHub Pages, citations, and dependency updates.

## Validation gates

For every data or evidence change, run:

```powershell
python scripts/validate_repository.py
node --check assets/app.js
node --check data/catalogue.js
node --check data/evidence.js
```

Also perform task-specific checks:

- View representative evidence images, including every newly added or corrected recording.
- For a disputed frame, compare the exact named source plus nearby frames and any source variants.
- Confirm `git diff --name-only` contains only intended generated sets.
- Serve the repository through a local HTTP server when changing navigation or runtime loading; opening `index.html` directly is useful but does not reproduce every browser security rule.
- After pushing, require the Pages workflow to succeed and verify the live site, generated data, manifest, and at least one changed image return HTTP 200.

The validator checks structural invariants, not semantic correctness. A passing result does not replace visual review.

## Site editing conventions

- Use plain HTML, CSS, and browser JavaScript; do not introduce a framework or package manager without an explicit architectural decision.
- Keep user-facing counts derived from data rather than hard-coded where practical.
- Preserve keyboard access, dialog close behavior, visible focus, alt text, responsive layouts, and reduced-motion expectations.
- Load only the evidence for the selected glyph in the interface; do not eagerly render all 768 images.
- Keep generated JSON readable and generated JavaScript compact.
- Do not hand-edit `catalogue.js` or `evidence.js` independently of their JSON counterparts.

## Provenance and source additions

Every new source must record, at minimum:

- logical broadcast label;
- exact source filename and extension;
- original URL or provider and acquisition date when available;
- SHA-256 of the raw file in the private source ledger;
- codec, frame rate, dimensions, duration, and decoded frame count;
- whether the file is original, transcoded, cropped, zoomed, or otherwise derived;
- which exact file the frame indices were generated against;
- contributor and tagging/classification method;
- license or rights note sufficient to explain why raw media is or is not committed.

Update `SOURCES.md`, `credits.html`, and `NOTICE.md` when the new source changes their claims. Do not cite a repository merely because it informed a hypothesis; state how it was actually used.

## GitHub and release maintenance

- Work on a `codex/` branch unless the maintainer explicitly asks for direct work on `main`.
- Keep data regeneration and unrelated interface redesigns in separate commits when possible.
- Never force-push over collaborator changes. Fetch and inspect remote commits before rebasing or merging.
- GitHub Pages deploys on every push to `main`; no manual branch-pages configuration is required for this workflow.
- Dependabot checks GitHub Actions weekly and groups all available version updates into one pull request named by the `all-github-actions` group.
- Review grouped updates as a unit, confirm action majors are expected, merge, and verify the Pages workflow.

## Completion report

When handing off a change, report:

- what source/data/site records changed;
- whether records are manual or provisional;
- exact source filenames and frame ranges affected;
- validation commands and results;
- live deployment status and commit/PR link when publishing occurred;
- remaining uncertainties requiring human visual review.
