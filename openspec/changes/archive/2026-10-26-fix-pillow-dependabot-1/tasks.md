## 1. Remediation

- [x] Inspect alert 1 and confirm the patched release using GitHub and PyPI metadata.
- [x] Reproduce rejected GIF dimensions on Pillow 12.2.0 in a memory-limited Podman container without oversized allocation.
- [x] Hash-pin patched Pillow and compatible NumPy releases, preserving Python 3.11 support.
- [x] Add the safe regression test to validation CI and document installation.
- [x] Verify hash-checked installs, regression checks and pipeline imports on Python 3.11, 3.12 and 3.14.
- [x] Run repository validation, JavaScript syntax checks and whitespace validation.
