from __future__ import annotations

import csv
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import find_executable, load_config, read_csv, run, sample_frames


DIAMOND = {
    (0, 4),
    (1, 3), (1, 4), (1, 5),
    (2, 2), (2, 3), (2, 5), (2, 6),
    (3, 1), (3, 2), (3, 6), (3, 7),
    (4, 0), (4, 1), (4, 7), (4, 8),
    (5, 1), (5, 2), (5, 6), (5, 7),
    (6, 2), (6, 3), (6, 5), (6, 6),
    (7, 3), (7, 4), (7, 5),
    (8, 4),
}
USABLE = [(row, column) for row in range(9) for column in range(9) if (row, column) not in DIAMOND]


def load_dictionary(path: Path):
    rows = []
    for row in read_csv(path):
        bits = np.array([int(row[f"r{r}c{c}"]) for r in range(9) for c in range(9)], dtype=np.uint8)
        rows.append((int(row["glyph_id"]), bits))
    if not rows:
        raise ValueError(f"Empty glyph dictionary: {path}")
    return rows, np.stack([item[1] for item in rows])


def ring_values(gray: np.ndarray, pitch: float, center_x: float, center_y: float) -> np.ndarray:
    angles = np.arange(32, dtype=np.float32) * (2 * np.pi / 32)
    radii = np.array([0.39, 0.42, 0.45], dtype=np.float32) * pitch
    rr, aa = np.meshgrid(radii, angles, indexing="ij")
    dx = (np.cos(aa) * rr).ravel()
    dy = (np.sin(aa) * rr).ravel()
    centers_x = np.array([center_x + (column - 4) * pitch for row in range(9) for column in range(9)], dtype=np.float32)
    centers_y = np.array([center_y + (row - 4) * pitch for row in range(9) for column in range(9)], dtype=np.float32)
    xs = np.rint(centers_x[:, None] + dx[None, :]).astype(np.int32)
    ys = np.rint(centers_y[:, None] + dy[None, :]).astype(np.int32)
    valid = (xs >= 0) & (ys >= 0) & (xs < gray.shape[1]) & (ys < gray.shape[0])
    values = np.full(xs.shape, 255, dtype=np.float32)
    values[valid] = gray[ys[valid], xs[valid]]
    return values.reshape(9, 9, -1)


def estimate_pitch(gray: np.ndarray) -> float:
    bright = (gray[100:960:2, 100:960:2] > 100).astype(np.float32)
    scores = []
    for lag in range(22, 59):
        horizontal = float(np.mean(bright[:, :-lag] * bright[:, lag:]))
        vertical = float(np.mean(bright[:-lag, :] * bright[lag:, :]))
        scores.append((horizontal + vertical, lag * 2.0))
    return max(scores)[1]


def geometry_score(gray: np.ndarray, pitch: float, center_x: float, center_y: float) -> float:
    means = ring_values(gray, pitch, center_x, center_y).mean(axis=2)
    return float(np.median(means) + 0.10 * np.quantile(means, 0.75))


def calibrate_center(gray: np.ndarray):
    pitch_zero = estimate_pitch(gray)
    candidates = []
    for pitch in np.arange(pitch_zero - 6, pitch_zero + 6.01, 0.5):
        for center_x in range(532, 549, 2):
            for center_y in range(522, 539, 2):
                score = geometry_score(gray, pitch, center_x, center_y)
                candidates.append((score, -abs(pitch - pitch_zero), -abs(center_x - 540), -abs(center_y - 530), pitch, float(center_x), float(center_y)))
    return max(candidates)[4:]


def fit_pitch(gray: np.ndarray, center_x: float, center_y: float) -> float:
    pitch_zero = estimate_pitch(gray)
    candidates = []
    for pitch in np.arange(pitch_zero - 6, pitch_zero + 6.01, 0.5):
        candidates.append((geometry_score(gray, pitch, center_x, center_y), -abs(pitch - pitch_zero), pitch))
    return max(candidates)[2]


def classify(gray, pitch, center_x, center_y, dictionary, dictionary_bits):
    values = ring_values(gray, pitch, center_x, center_y)
    fractions = (values < 80).mean(axis=2)
    marks = {(row, column) for row, column in USABLE if fractions[row, column] > 0.50}
    bits = np.array([1 if (row, column) in marks else 0 for row in range(9) for column in range(9)], dtype=np.uint8)
    distances = np.count_nonzero(dictionary_bits != bits[None, :], axis=1)
    nearest_index = int(np.argmin(distances))
    usable_fractions = fractions[[row for row, column in USABLE], [column for row, column in USABLE]]
    return marks, bits, fractions, dictionary[nearest_index][0], int(distances[nearest_index]), float(np.mean(np.abs(usable_fractions - 0.5)))


def extract_frames(ffmpeg: str, video: Path, frames: list[int], temp_dir: Path) -> dict[int, Path]:
    selected = "+".join(f"eq(n\\,{frame})" for frame in frames)
    video_filter = (
        f"select={selected},"
        "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',"
        "scale=1080:1080:flags=lanczos"
    )
    run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", video_filter, "-fps_mode", "vfr", "-q:v", "2", str(temp_dir / "frame_%04d.jpg"),
    ])
    extracted = sorted(temp_dir.glob("frame_*.jpg"))
    if len(extracted) != len(frames):
        raise RuntimeError(f"Expected {len(frames)} frames from {video.name}, extracted {len(extracted)}")
    return dict(zip(frames, extracted))


def render_grid(marks, path: Path, label: str) -> None:
    cell, margin = 42, 48
    image = Image.new("RGB", (cell * 9 + margin * 2, cell * 9 + margin + 72), "#0b0b0b")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    draw.text((margin, 12), label, fill="white", font=font)
    for row in range(9):
        for column in range(9):
            x, y = margin + column * cell, 48 + row * cell
            if (row, column) in DIAMOND:
                fill, outline = "#0b0b0b", "#fafae5"
            elif (row, column) in marks:
                fill, outline = "#ff4700", "#fafae5"
            else:
                fill, outline = "#0b0b0b", "#fafae5"
            draw.rectangle((x + 2, y + 2, x + cell - 3, y + cell - 3), fill=fill, outline=outline, width=2)
    image.save(path)


def render_contact_sheet(output: Path, recording_rows: list[dict], analysis_dir: Path) -> None:
    thumbs = []
    font = ImageFont.load_default(size=14)
    for row in recording_rows:
        image = Image.open(analysis_dir / row["frame_file"]).convert("RGB")
        image.thumbnail((340, 340))
        canvas = Image.new("RGB", (360, 405), "#0b0b0b")
        canvas.paste(image, ((360 - image.width) // 2, 40))
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 8), f"#{row['glyph_index']} f{row['frame']} {row['time_s']}s", fill="white", font=font)
        draw.text((8, 375), f"{row['n_cells']} cells | nearest #{row['nearest_glyph_id']} d={row['hamming_distance']}", fill="#ff4700", font=font)
        thumbs.append(canvas)
    columns = 5
    sheet = Image.new("RGB", (columns * 360, math.ceil(len(thumbs) / columns) * 405), "black")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 360, (index // columns) * 405))
    sheet.save(output, quality=92)


def expected_rows(archive_invest: Path, broadcast: str):
    path = archive_invest / "PatternCSVs" / f"{broadcast}_patterns.csv"
    if not path.is_file():
        return []
    result = []
    for row in read_csv(path):
        bits = np.array([int(row[f"r{r}c{c}"]) for r in range(9) for c in range(9)], dtype=np.uint8)
        result.append((int(float(row["frame"])), bits))
    return result


def analyze(config_path: Path, archive_invest: Path, video_dir: Path, analysis_dir: Path, ffmpeg_path: str | None = None) -> dict:
    config = load_config(config_path)
    ffmpeg = find_executable(ffmpeg_path, "ffmpeg")
    dictionary, dictionary_bits = load_dictionary(archive_invest / "PatternCSVs" / "glyph_dictionary.csv")
    frames_root = analysis_dir / "frames"
    grids_root = analysis_dir / "binary_grids"
    sheets_root = analysis_dir / "contact_sheets"
    for directory in (analysis_dir, frames_root, grids_root, sheets_root):
        directory.mkdir(parents=True, exist_ok=True)

    all_rows, calibration = [], []
    geometry = {}
    for source in config.get("automatic_sources", []):
        broadcast = source["broadcast"]
        video = video_dir / source["file"]
        if not video.is_file():
            raise FileNotFoundError(video)
        frames = sample_frames(source)
        with tempfile.TemporaryDirectory(prefix=f"glyph-{broadcast}-") as temp_name:
            extracted = extract_frames(ffmpeg, video, frames, Path(temp_name))
            calibration_frame = frames[max(0, len(frames) - 3)]
            calibration_gray = np.asarray(Image.open(extracted[calibration_frame]).convert("L"), dtype=np.uint8)
            _, center_x, center_y = calibrate_center(calibration_gray)
            geometry[broadcast] = {"center_x": center_x, "center_y": center_y}
            frame_out, grid_out = frames_root / broadcast, grids_root / broadcast
            frame_out.mkdir(parents=True, exist_ok=True)
            grid_out.mkdir(parents=True, exist_ok=True)
            known_rows = expected_rows(archive_invest, broadcast)
            recording_rows = []
            for ordinal, frame in enumerate(frames, 1):
                image = Image.open(extracted[frame]).convert("RGB")
                gray = np.asarray(image.convert("L"), dtype=np.uint8)
                pitch = fit_pitch(gray, center_x, center_y)
                marks, bits, fractions, nearest_id, distance, confidence = classify(gray, pitch, center_x, center_y, dictionary, dictionary_bits)
                fingerprint = "".join(str(int(bit)) for bit in bits)
                cells = " ".join(f"({row} {column})" for row, column in sorted(marks))
                output_name = f"glyph_{ordinal:02d}_f{frame:04d}.jpg"
                image.save(frame_out / output_name, format="JPEG", quality=95, optimize=True)
                render_grid(marks, grid_out / output_name.replace(".jpg", ".png"), f"{broadcast} #{ordinal}  f{frame}  nearest #{nearest_id} (d={distance})")
                row = {
                    "video": broadcast,
                    "glyph_index": ordinal,
                    "frame": frame,
                    "time_s": f"{frame / 30:.4f}",
                    "pitch_px": f"{pitch:.2f}",
                    "center_x": f"{center_x:.1f}",
                    "center_y": f"{center_y:.1f}",
                    "n_cells": len(marks),
                    "cells": cells,
                    "fingerprint": fingerprint,
                    "nearest_glyph_id": nearest_id,
                    "hamming_distance": distance,
                    "classification_confidence": f"{confidence:.4f}",
                    "frame_file": f"frames/{broadcast}/{output_name}",
                    "grid_file": f"binary_grids/{broadcast}/{output_name.replace('.jpg', '.png')}",
                }
                all_rows.append(row)
                recording_rows.append(row)
                if known_rows:
                    adjusted = frame - int(source.get("archive_offset", 0))
                    eligible = [item for item in known_rows if item[0] <= adjusted]
                    if eligible:
                        expected_frame, expected_bits = eligible[-1]
                        calibration.append({"video": broadcast, "local_frame": frame, "archive_frame": expected_frame, "hamming": int(np.count_nonzero(bits != expected_bits))})
            render_contact_sheet(sheets_root / f"{broadcast}.jpg", recording_rows, analysis_dir)
        print(f"Analysed {len(frames):>3} glyph frames: {broadcast} ({video.name})")

    if not all_rows:
        raise ValueError("No automatic sources configured")
    with (analysis_dir / "glyph_sequences.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    with (analysis_dir / "calibration.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["video", "local_frame", "archive_frame", "hamming"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(calibration)

    summary = {
        "total_selected_frames": len(all_rows),
        "unique_detected_patterns": len({row["fingerprint"] for row in all_rows}),
        "dictionary_size": len(dictionary),
        "geometry": geometry,
        "method": {
            "sample": "configured settled frame from each hold",
            "signal": "fraction of ring samples below luminance 80; marked if greater than 50%",
            "excluded_cells": "symmetric 28-cell carrier mask; (2,6) and (5,2) independently audited",
        },
    }
    (analysis_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract and classify configured provisional glyph sources.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg")
    arguments = parser.parse_args()
    result = analyze(arguments.config.resolve(), arguments.archive_invest.resolve(), arguments.video_dir.resolve(), arguments.analysis_dir.resolve(), arguments.ffmpeg)
    print(json.dumps(result, indent=2))
