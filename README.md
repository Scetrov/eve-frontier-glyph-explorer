# Frontier Archive Glyph Explorer

An unofficial, static explorer for the 9×9 glyph sequences found in EVE Frontier Archive broadcasts.

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
- `evidence/` contains one 480×480 audit image for each of the 768 occurrence records.
- The CSV files are downloadable from the Method section.

Every evidence record names its source video, exact source-frame number, timestamp, matching basis, and canonical/observed Hamming distance. The 181 automatically extracted local-video occurrences are marked provisional. Canonical dictionary patterns and manual tags are derived from [QZRChedders/ArchiveInvest](https://github.com/QZRChedders/ArchiveInvest).

Frame numbers are relative to the exact filename in each evidence record. In particular, the `E6C2-1K` pattern CSV was tagged against `E6C2-1K zoomed.mp4`, not the longer plain `E6C2-1K.mp4` source.

EVE Frontier and associated marks belong to their respective owners. This community research tool is not affiliated with or endorsed by the game's creators.
