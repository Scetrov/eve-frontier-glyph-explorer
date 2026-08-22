---
name: eve-glyph-publish-site
description: Maintain and publish the static EVE Frontier Glyph Explorer, including UI edits, generated-data loading, accessibility, credits, GitHub Pages verification, and grouped Dependabot updates. Use for site changes, releases, deployment failures, or dependency-maintenance work.
license: MIT
---

# Maintain and publish the Glyph Explorer

When working in the Glyph Explorer repository, read the root `AGENTS.md`. The production site is the repository root served by GitHub Pages; there is no frontend build.

Local checks require git and Node.js. Publishing requires GitHub access and the GitHub CLI or equivalent.

## Make static-site changes

- Preserve the loading order: `catalogue.js`, `evidence.js`, then `app.js`.
- Keep project-relative URLs; never assume `/` is the repository root on the deployed domain.
- Keep `catalogue.json`/`catalogue.js` and `evidence.json`/`evidence.js` synchronized.
- Avoid frameworks and runtime dependencies unless the maintainer explicitly approves an architectural change.
- Preserve keyboard navigation, visible focus, dialog escape/backdrop behavior, semantic labels, image alt text, responsive layout, and readable contrast.
- Do not eagerly load all evidence images. Render the selected glyph's occurrences only.
- Keep counts data-driven and distinguish manual from provisional records in user-facing text.

## Maintain provenance

When data sources, contributors, or tools change, update `SOURCES.md`, `credits.html`, and where appropriate `NOTICE.md`. The MIT license applies only to original site code. Do not imply CCP Games, Fenris Creations, ArchiveInvest, or supporting datasets endorse the site.

## Validate locally

Run:

```powershell
python scripts/validate_repository.py
node --check assets/app.js
node --check data/catalogue.js
node --check data/evidence.js
```

For a data release, also run `pipeline/inventory_sources.py --verify` against the exact local directories used for the build. Do not publish a newly generated manifest if any input differs unexpectedly.

For runtime changes, serve the repository rather than relying only on a direct file open:

```powershell
python -m http.server 8000
```

Check filtering, glyph selection, evidence thumbnails, modal open/close, downloads, credits, keyboard behavior, and narrow viewport layout.

## Review and commit

Inspect `git status`, the complete diff, and unexpected binary changes. Fetch before pushing; if remote `main` advanced, inspect and integrate its commits without force-pushing. Keep generated data changes and unrelated styling changes separable when possible.

## Publish

Push the reviewed commit to `main` only when authorized. The `Deploy static site to Pages` workflow uploads the repository and deploys GitHub Pages.

Require the workflow to complete successfully. Then verify:

- explorer root returns HTTP 200;
- `data/catalogue.js`, `data/evidence.js`, the evidence manifest, and `data/source_integrity.json` return HTTP 200;
- the live integrity manifest SHA-256 matches the committed manifest;
- at least one changed evidence image returns HTTP 200;
- changed live assets match the committed files when cache propagation matters.

## Dependabot

`.github/dependabot.yml` monitors the `github-actions` ecosystem weekly. The `all-github-actions` group uses `patterns: ["*"]` and `open-pull-requests-limit: 1`, so all available version updates are proposed together.

When reviewing the grouped PR:

1. inspect every action and major-version change in the workflow diff;
2. retain least-privilege Pages permissions;
3. merge only after the deployment workflow is expected to remain compatible;
4. verify the Pages run produced by the merge.

Dependabot does not justify merging unrelated behavior changes without review.

## Handoff

Report the commit or PR, changed areas, validation output, Pages run result, live URL, and any outstanding manual visual review.
