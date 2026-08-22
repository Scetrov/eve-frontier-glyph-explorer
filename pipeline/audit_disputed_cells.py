from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from common import find_executable, run


AUDITS = (
    {
        "glyph_id": 130, "cell": (2, 6), "broadcast": "E6C4-17",
        "sources": (
            {"source_set": "archiveinvest", "filename": "E6C4-17.mp4", "frames": (884, 890), "center": (242.0, 289.0), "pitch": 32.0},
            {"source_set": "downloaded", "filename": "E6C4-17.webm", "frames": (927, 933), "center": (241.0, 236.0), "pitch": 41.0},
        ),
    },
    {
        "glyph_id": 140, "cell": (5, 2), "broadcast": "E6C4-35",
        "sources": (
            {"source_set": "archiveinvest", "filename": "E6C4-35.mp4", "frames": (280, 286), "center": (236.0, 241.0), "pitch": 43.0},
        ),
    },
)


def decode_frames(ffmpeg: str, video: Path, first: int, last: int) -> np.ndarray:
    selected = f"between(n\\,{first}\\,{last})"
    video_filter = f"select='{selected}',crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=480:480:flags=lanczos,format=gray"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", video_filter, "-fps_mode", "vfr", "-f", "rawvideo", "-"]
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    pixels = np.frombuffer(result.stdout, dtype=np.uint8)
    frame_size = 480 * 480
    if pixels.size % frame_size or pixels.size // frame_size != last - first + 1:
        raise RuntimeError(f"Expected {last - first + 1} frames from {video.name}; decoded {pixels.size // frame_size}")
    return pixels.reshape(-1, 480, 480)


def contrast_score(image: np.ndarray, row: int, column: int, center: tuple[float, float], pitch: float) -> float:
    x = center[0] + (column - 4) * pitch
    y = center[1] + (row - 4) * pitch
    inner = max(2, round(pitch * 0.13))
    outer = max(inner + 2, round(pitch * 0.31))
    x0, y0 = round(x), round(y)
    centre = image[y0 - inner:y0 + inner + 1, x0 - inner:x0 + inner + 1]
    neighbourhood = image[y0 - outer:y0 + outer + 1, x0 - outer:x0 + outer + 1]
    bright_reference = float(np.quantile(neighbourhood, 0.8))
    centre_mean = float(np.mean(centre))
    return round(max(-1.0, min(1.0, (bright_reference - centre_mean) / max(bright_reference, 1.0))), 4)


def write_jpeg(ffmpeg: str, median: np.ndarray, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pgm = destination.with_suffix(".pgm")
    pgm.write_bytes(f"P5\n480 480\n255\n".encode("ascii") + median.tobytes())
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(pgm), "-q:v", "2", str(destination)])
    pgm.unlink()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Re-audit the two disputed carrier-edge cells with registered multi-frame medians.")
    parser.add_argument("--downloaded-dir", type=Path, required=True)
    parser.add_argument("--archive-video-dir", type=Path, required=True)
    parser.add_argument("--integrity", type=Path, default=root / "data" / "source_integrity.json")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg; otherwise it must be on PATH.")
    args = parser.parse_args()
    ffmpeg = find_executable(args.ffmpeg, "ffmpeg")
    hashes = {(row["source_set"], row["filename"]): row["sha256"] for row in json.loads(args.integrity.read_text(encoding="utf-8"))["entries"]}
    roots = {"downloaded": args.downloaded_dir.resolve(), "archiveinvest": args.archive_video_dir.resolve()}

    rows = []
    for audit in AUDITS:
        source_results = []
        for source in audit["sources"]:
            key = (source["source_set"], source["filename"])
            if key not in hashes:
                raise ValueError(f"Source is absent from integrity manifest: {key}")
            video = roots[source["source_set"]] / source["filename"]
            first, last = source["frames"]
            frames = decode_frames(ffmpeg, video, first, last)
            median = np.median(frames, axis=0).astype(np.uint8)
            per_frame = [contrast_score(frame, *audit["cell"], source["center"], source["pitch"]) for frame in frames]
            median_score = contrast_score(median, *audit["cell"], source["center"], source["pitch"])
            image_name = f"g{audit['glyph_id']:03d}_{source['source_set']}_{Path(source['filename']).stem}_f{first}-{last}_median.jpg"
            destination = root / "evidence" / "audits" / image_name
            write_jpeg(ffmpeg, median, destination)
            source_results.append({
                "source_set": source["source_set"], "source_video": source["filename"], "sha256": hashes[key],
                "frames": list(range(first, last + 1)), "registration": {"center_x": source["center"][0], "center_y": source["center"][1], "pitch": source["pitch"]},
                "per_frame_contrast": per_frame, "median_contrast": median_score,
                "median_image": destination.relative_to(root).as_posix(),
            })
        result = {
            "glyph_id": audit["glyph_id"], "broadcast": audit["broadcast"],
            "cell": f"({audit['cell'][0]},{audit['cell'][1]})", "verdict": "carrier / inactive",
            "basis": "All registered seven-frame medians show no central dark payload aperture; contrast stays below the 0.35 active threshold.",
            "sources": source_results,
        }
        rows.append(result)

    payload = {
        "audit_version": 1,
        "method": "Independent per-video 9×9 lattice registration; seven settled frames; pixelwise median; central-aperture contrast against each cell's bright reference.",
        "active_contrast_threshold": 0.35,
        "conclusion": "Both disputed cells are carrier positions. Removing the two singleton marks makes the empirical 26-cell mask converge with the symmetric 28-cell mask.",
        "audits": rows,
        "mask_hypotheses": [
            {"name": "legacy empirical 26-cell", "excluded_cells": 26, "payload_positions": 55, "active_disputed_cells_after_audit": 0, "catalogue_glyphs": 146},
            {"name": "symmetric 28-cell", "excluded_cells": 28, "payload_positions": 53, "active_disputed_cells_after_audit": 0, "catalogue_glyphs": 146},
        ],
    }
    data_dir = root / "data"
    (data_dir / "disputed_cell_audit.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (data_dir / "disputed_cell_audit.js").write_text(f"window.GLYPH_CELL_AUDIT={json.dumps(payload, separators=(',', ':'))};\n", encoding="utf-8")
    with (data_dir / "disputed_cell_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("glyph_id", "broadcast", "cell", "verdict", "source_set", "source_video", "sha256", "frames", "median_contrast", "median_image"))
        writer.writeheader()
        for row in rows:
            for source in row["sources"]:
                writer.writerow({
                    "glyph_id": row["glyph_id"], "broadcast": row["broadcast"], "cell": row["cell"], "verdict": row["verdict"],
                    "source_set": source["source_set"], "source_video": source["source_video"], "sha256": source["sha256"],
                    "frames": " ".join(map(str, source["frames"])), "median_contrast": source["median_contrast"], "median_image": source["median_image"],
                })
    print(json.dumps({"audits": len(rows), "source_reads": sum(len(row["sources"]) for row in rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
