# Fix Pillow Dependabot alert 1

## Why

Dependabot alert [1](https://github.com/Scetrov/eve-frontier-glyph-explorer/security/dependabot/1) reports GHSA-65qm-jvmh-6pqg / CVE-2026-112400. The pipeline's Pillow upper bound excludes the first patched release, 13.0.0.

## What Changes

- Pin Pillow 13.0.0 and verify release artifact SHA-256 hashes during installation.
- Pin NumPy too, as pip hash-checking requires every dependency to be pinned and hashed; preserve Python 3.11 with NumPy 2.3.5 and use NumPy 2.5.4 on Python 3.12+.
- Add a safe GIF rejection regression check and execute it in validation CI.
- Document the dependency installation and check.

## Impact

Only offline pipeline dependencies, tests, and documentation change. The static browser runtime, source registry, manual/provisional records, exact filenames and frame references remain unchanged. No media rebuild or live deployment is required for this PR.

## Non-goals

No dependency overhaul for optional vision experiments, UI changes, or claim that the application exposes a GIF upload service.
