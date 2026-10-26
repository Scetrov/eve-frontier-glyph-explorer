## ADDED Requirements

### Requirement: Verified pipeline image dependencies

Pipeline dependencies SHALL install from exact versions with SHA-256 verification, include Pillow 13.0.0 or a reviewed later patched release, and retain Python 3.11 compatibility.

#### Scenario: Installing the pipeline

- **WHEN** a maintainer installs `pipeline/requirements.txt`
- **THEN** pip verifies the selected release artifact hashes and rejects unlisted artifacts
- **AND** Pillow is not in the vulnerable range for GHSA-65qm-jvmh-6pqg

### Requirement: Safe GIF rejection regression check

CI SHALL verify that rejecting an oversized later GIF frame preserves the original image dimensions without attempting a subsequent oversized allocation.

#### Scenario: Rejected GIF extent

- **WHEN** a one-pixel GIF is opened and seeking a later 40000-by-40000 frame raises `DecompressionBombError`
- **THEN** the image size remains one pixel by one pixel
- **AND** the test does not retry loading the rejected frame
