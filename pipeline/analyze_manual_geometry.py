"""Record blind lattice and payload-read candidates for manual corpus frames.

This is deliberately a review producer, not an overlay publisher. ArchiveInvest
manual tags do not carry detector coordinates, so a candidate must be reviewed
before it can be promoted into evidence.json. Corpus tags are compared only after
the image read and never influence geometry or classification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from analyze_sources import DIAMOND, ring_values
from common import fingerprint_from_cells, find_executable, load_config, parse_cells, read_csv, resolve_manual_video, run


def grid_line_fit(image_path: Path) -> dict[str, float]:
    """Fit repeated vertical/horizontal cell borders without consulting a glyph tag."""
    with Image.open(image_path) as image:
        gray = np.asarray(image.convert("L"), dtype=np.float32)
    edge_x = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    edge_y = np.abs(np.diff(gray, axis=0)).mean(axis=1)
    pitches = np.arange(18.0, 64.01, 0.5)
    centres = np.arange(96.0, 384.01, 1.0)
    offsets = np.arange(10, dtype=np.float32) - 4.5

    def fit(projection: np.ndarray) -> tuple[float, float, float]:
        candidates = []
        for pitch in pitches:
            positions = centres[:, None] + offsets[None, :] * pitch
            indices = np.clip(np.rint(positions).astype(np.int32), 0, len(projection) - 1)
            scores = projection[indices].mean(axis=1)
            index = int(np.argmax(scores))
            candidates.append((float(scores[index]), float(pitch), float(centres[index])))
        return max(candidates)

    score_x, pitch_x, center_x = fit(edge_x)
    score_y, pitch_y, center_y = fit(edge_y)
    return {
        "center_x": round(center_x, 4), "center_y": round(center_y, 4),
        "pitch_x": round(pitch_x, 4), "pitch_y": round(pitch_y, 4),
        "fit_score_x": round(score_x, 4), "fit_score_y": round(score_y, 4),
    }


def blind_payload_read(image_path: Path, fit: dict[str, float]) -> tuple[str, float]:
    """Read cell states from the independent lattice before comparing with a tag."""
    with Image.open(image_path) as image:
        gray = np.asarray(image.convert("L"), dtype=np.uint8)
    pitch = (fit["pitch_x"] + fit["pitch_y"]) / 2
    values = ring_values(gray, pitch, fit["center_x"], fit["center_y"])
    fractions = (values < 80).mean(axis=2)
    bits = [
        "0" if (row, column) in DIAMOND else ("1" if fractions[row, column] > 0.50 else "0")
        for row in range(9) for column in range(9)
    ]
    usable = [fractions[row, column] for row in range(9) for column in range(9) if (row, column) not in DIAMOND]
    confidence = float(np.mean(np.abs(np.asarray(usable) - 0.5)))
    return "".join(bits), round(confidence, 4)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Create independent manual-frame lattice review candidates.")
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--output", type=Path, default=root / "data" / "manual_geometry_review.json")
    args = parser.parse_args()
    config, ffmpeg = load_config(root / "pipeline" / "corpus.json"), find_executable(args.ffmpeg, "ffmpeg")
    integrity = json.loads((root / "data" / "source_integrity.json").read_text(encoding="utf-8"))
    hashes = {row["filename"]: row["sha256"] for row in integrity["entries"]}
    rows = []
    for pattern in sorted((args.archive_invest / "PatternCSVs").glob("*_patterns.csv")):
        recording = pattern.stem.removesuffix("_patterns")
        video = resolve_manual_video(args.archive_invest, recording, config)
        pattern_rows = read_csv(pattern)
        frames = [int(float(row["frame"])) for row in pattern_rows]
        with tempfile.TemporaryDirectory(prefix="manual-geometry-") as temporary:
            target = Path(temporary)
            selection = "+".join(f"eq(n\\,{frame})" for frame in dict.fromkeys(frames))
            filters = f"select={selection},crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=480:480:flags=lanczos"
            run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", filters, "-fps_mode", "vfr", "-q:v", "2", str(target / "frame_%04d.jpg")])
            images = dict(zip(dict.fromkeys(frames), sorted(target.glob("frame_*.jpg"))))
            for ordinal, (frame, pattern_row) in enumerate(zip(frames, pattern_rows), 1):
                fit = grid_line_fit(images[frame])
                detected, confidence = blind_payload_read(images[frame], fit)
                corpus = fingerprint_from_cells(parse_cells(pattern_row.get("cells", "")))
                distance = sum(left != right for left, right in zip(detected, corpus))
                comparison = "exact support" if distance == 0 else "near support" if distance <= 2 else "disagreement"
                rows.append({
                    "recording": recording, "ordinal": ordinal, "frame": frame,
                    "source_video": video.name, "source_sha256": hashes.get(video.name),
                    "method": "independent-grid-line-plus-ring-read-v1",
                    "review_status": "pending", "overlay_enabled": False,
                    "corpus_fingerprint": corpus, "detected_fingerprint": detected,
                    "hamming_to_corpus": distance, "detector_separation": confidence,
                    "comparison": comparison, **fit,
                })
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".js").write_text(
        f"window.MANUAL_GEOMETRY_REVIEW={json.dumps(rows, separators=(',', ':'))};\n", encoding="utf-8"
    )
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = {
        "rows": len(rows),
        "exact_support": sum(row["comparison"] == "exact support" for row in rows),
        "near_support": sum(row["comparison"] == "near support" for row in rows),
        "disagreement": sum(row["comparison"] == "disagreement" for row in rows),
        "output": str(args.output),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
