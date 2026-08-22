"""Evaluate LoFTR reference-frame registration without changing catalogue data.

This is an experimental review producer. It verifies source and model hashes,
extracts exact decoded frames, estimates one homography per target, and compares
projected grid corners with manual geometry labels. Corpus fingerprints and glyph
IDs are deliberately never loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import cv2
import kornia
import numpy as np
import torch
from kornia.feature import LoFTR


MARTIAN_RED = (0, 71, 255)  # OpenCV BGR for #ff4700
NEUTRAL = (229, 250, 250)  # OpenCV BGR for #fafae5
DIM = (104, 104, 100)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def extract_frame(ffmpeg: Path, video: Path, frame: int, image_size: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        return
    filters = (
        f"select=eq(n\\,{frame}),"
        "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',"
        f"scale={image_size}:{image_size}:flags=lanczos"
    )
    run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", filters, "-fps_mode", "vfr", "-frames:v", "1", str(output),
    ])
    if not output.exists():
        raise RuntimeError(f"FFmpeg did not extract decoded frame {frame} from {video.name}")


def image_tensor(path: Path, device: torch.device) -> torch.Tensor:
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Could not read {path}")
    return torch.from_numpy(gray).to(device=device, dtype=torch.float32)[None, None] / 255.0


def load_model(checkpoint_path: Path, expected_sha256: str, device: torch.device) -> LoFTR:
    actual = sha256(checkpoint_path)
    if actual != expected_sha256:
        raise RuntimeError(f"LoFTR checkpoint SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model = LoFTR(pretrained=None)
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval().to(device)


def normalized_corners(sample: dict, image_size: int) -> np.ndarray:
    return np.asarray(sample["grid_corners_normalized"], dtype=np.float32) * image_size


def project_points(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(points.reshape(1, -1, 2), homography).reshape(-1, 2)


def reprojection_errors(source: np.ndarray, target: np.ndarray, homography: np.ndarray) -> np.ndarray:
    return np.linalg.norm(project_points(source, homography) - target, axis=1)


def dashed_line(image: np.ndarray, start: np.ndarray, end: np.ndarray, color: tuple[int, int, int]) -> None:
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length == 0:
        return
    direction = delta / length
    for offset in np.arange(0, length, 12.0):
        a = start + direction * offset
        b = start + direction * min(offset + 6.0, length)
        cv2.line(image, tuple(np.rint(a).astype(int)), tuple(np.rint(b).astype(int)), color, 1, cv2.LINE_AA)


def grid_segments(corners: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    top_left, top_right, bottom_right, bottom_left = corners
    segments = []
    for step in range(10):
        fraction = step / 9
        segments.append((top_left * (1 - fraction) + top_right * fraction,
                         bottom_left * (1 - fraction) + bottom_right * fraction))
        segments.append((top_left * (1 - fraction) + bottom_left * fraction,
                         top_right * (1 - fraction) + bottom_right * fraction))
    return segments


def render_result(
    target_path: Path,
    target_points: np.ndarray,
    inlier_mask: np.ndarray,
    predicted_grid: np.ndarray,
    expected_grid: np.ndarray,
    title: str,
    metrics: dict,
    output: Path,
) -> None:
    image = cv2.imread(str(target_path), cv2.IMREAD_COLOR)
    for point in target_points[inlier_mask][::max(1, int(inlier_mask.sum()) // 80)]:
        cv2.circle(image, tuple(np.rint(point).astype(int)), 1, DIM, -1, cv2.LINE_AA)
    for start, end in grid_segments(predicted_grid):
        cv2.line(image, tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int)), MARTIAN_RED, 1, cv2.LINE_AA)
    for index in range(4):
        dashed_line(image, expected_grid[index], expected_grid[(index + 1) % 4], NEUTRAL)

    header = np.full((72, image.shape[1], 3), (11, 11, 11), dtype=np.uint8)
    cv2.putText(header, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.48, NEUTRAL, 1, cv2.LINE_AA)
    summary = (
        f"matches {metrics['matches']} / inliers {metrics['inliers']} / "
        f"corner RMSE {metrics['manual_corner_rmse_px']:.2f}px / {'PASS' if metrics['accepted'] else 'REJECT'}"
    )
    cv2.putText(header, summary, (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.38, MARTIAN_RED, 1, cv2.LINE_AA)
    cv2.putText(header, "orange: LoFTR projection  pale dashed: manual geometry", (12, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, NEUTRAL, 1, cv2.LINE_AA)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), np.vstack((header, image)), [cv2.IMWRITE_JPEG_QUALITY, 92])


def accepted(metrics: dict, thresholds: dict) -> bool:
    return (
        metrics["matches"] >= thresholds["minimum_matches"]
        and metrics["inliers"] >= thresholds["minimum_inliers"]
        and metrics["inlier_ratio"] >= thresholds["minimum_inlier_ratio"]
        and metrics["median_reprojection_error_px"] <= thresholds["maximum_median_reprojection_error_px"]
        and metrics["manual_corner_rmse_px"] <= thresholds["maximum_manual_corner_rmse_px"]
    )


def strategy_mask(strategy: str, points: np.ndarray, reference_grid: np.ndarray) -> np.ndarray:
    if strategy == "all-correspondences":
        return np.ones(len(points), dtype=bool)
    if strategy == "reference-carrier-only":
        left, top = reference_grid.min(axis=0)
        right, bottom = reference_grid.max(axis=0)
        return ((points[:, 0] < left) | (points[:, 0] > right)
                | (points[:, 1] < top) | (points[:, 1] > bottom))
    raise ValueError(f"Unknown match strategy: {strategy}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the isolated LoFTR registration feasibility spike.")
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=root / "pipeline" / "vision_spike_config.json")
    parser.add_argument("--output-dir", type=Path, default=root / ".pipeline-work" / "vision-spike" / "run")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    integrity = json.loads((root / "data" / "source_integrity.json").read_text(encoding="utf-8"))
    source_hashes = {entry["filename"]: entry["sha256"] for entry in integrity["entries"]}
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else ("cpu" if args.device == "auto" else args.device)
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but this PyTorch build cannot use it")
    device = torch.device(device_name)
    model = load_model(args.checkpoint, config["checkpoint"]["sha256"], device)
    image_size = int(config["image_size"])
    frame_dir = args.output_dir / "frames"
    render_dir = args.output_dir / "renders"
    results = []

    for source in config["sources"]:
        base = args.archive_invest / "Videos" if source["location"] == "archive-invest" else args.video_dir
        video = base / source["source_video"]
        if not video.exists():
            raise FileNotFoundError(video)
        expected_source_hash = source_hashes.get(video.name)
        if expected_source_hash is None:
            raise RuntimeError(f"{video.name} is absent from data/source_integrity.json")
        actual_source_hash = sha256(video)
        if actual_source_hash != expected_source_hash:
            raise RuntimeError(f"Source SHA-256 mismatch for {video.name}")
        samples = {int(sample["frame"]): sample for sample in source["samples"]}
        reference_frame = int(source["reference_frame"])
        reference_image = frame_dir / f"{source['recording']}_f{reference_frame:06d}.png"
        extract_frame(args.ffmpeg, video, reference_frame, image_size, reference_image)
        reference_tensor = image_tensor(reference_image, device)
        reference_grid = normalized_corners(samples[reference_frame], image_size)

        for frame, sample in samples.items():
            if frame == reference_frame:
                continue
            target_image = frame_dir / f"{source['recording']}_f{frame:06d}.png"
            extract_frame(args.ffmpeg, video, frame, image_size, target_image)
            started = time.perf_counter()
            with torch.inference_mode():
                match = model({"image0": reference_tensor, "image1": image_tensor(target_image, device)})
            elapsed = time.perf_counter() - started
            points0 = match["keypoints0"].detach().cpu().numpy().astype(np.float32)
            points1 = match["keypoints1"].detach().cpu().numpy().astype(np.float32)
            if len(points0) < 4:
                raise RuntimeError(f"Only {len(points0)} LoFTR matches for {source['recording']} frame {frame}")
            for strategy in config["match_strategies"]:
                selected = strategy_mask(strategy, points0, reference_grid)
                selected0, selected1 = points0[selected], points1[selected]
                if len(selected0) < 4:
                    print(json.dumps({"recording": source["recording"], "target_frame": frame,
                                      "strategy": strategy, "error": "fewer than four selected matches"}))
                    continue
                homography, mask = cv2.findHomography(
                    selected0, selected1, cv2.USAC_MAGSAC, 2.5, maxIters=10000, confidence=0.999
                )
                if homography is None or mask is None:
                    print(json.dumps({"recording": source["recording"], "target_frame": frame,
                                      "strategy": strategy, "error": "homography estimation failed"}))
                    continue
                inlier_mask = mask.ravel().astype(bool)
                errors = reprojection_errors(selected0[inlier_mask], selected1[inlier_mask], homography)
                predicted_grid = project_points(reference_grid, homography)
                expected_grid = normalized_corners(sample, image_size)
                corner_errors = np.linalg.norm(predicted_grid - expected_grid, axis=1)
                metrics = {
                    "recording": source["recording"],
                    "source_video": video.name,
                    "source_sha256": actual_source_hash,
                    "reference_frame": reference_frame,
                    "target_frame": frame,
                    "strategy": strategy,
                    "loftr_matches": int(len(points0)),
                    "matches": int(len(selected0)),
                    "inliers": int(inlier_mask.sum()),
                    "inlier_ratio": round(float(inlier_mask.mean()), 4),
                    "median_reprojection_error_px": round(float(np.median(errors)), 4),
                    "p95_reprojection_error_px": round(float(np.percentile(errors, 95)), 4),
                    "manual_corner_rmse_px": round(float(np.sqrt(np.mean(corner_errors ** 2))), 4),
                    "manual_corner_max_error_px": round(float(corner_errors.max()), 4),
                    "elapsed_seconds": round(elapsed, 4),
                    "homography": np.round(homography, 8).tolist(),
                    "predicted_grid_corners": np.round(predicted_grid, 3).tolist(),
                    "manual_grid_corners": np.round(expected_grid, 3).tolist(),
                }
                metrics["accepted"] = accepted(metrics, config["acceptance"])
                render_name = (
                    f"{source['recording']}_f{reference_frame:06d}_to_f{frame:06d}_{strategy}.jpg"
                )
                metrics["render"] = f"renders/{render_name}"
                render_result(target_image, selected1, inlier_mask, predicted_grid, expected_grid,
                              f"{source['recording']} / {reference_frame} -> {frame} / {strategy}",
                              metrics, render_dir / render_name)
                results.append(metrics)
                print(json.dumps({key: metrics[key] for key in (
                    "recording", "target_frame", "strategy", "matches", "inliers",
                    "manual_corner_rmse_px", "accepted"
                )}))

    payload = {
        "schema_version": 1,
        "status": "experimental-not-canonical",
        "method": config["method"],
        "geometry_labels": "manual normalized grid corners; corpus bits and glyph IDs excluded",
        "checkpoint": {**config["checkpoint"], "local_sha256_verified": True},
        "environment": {
            "python": platform.python_version(), "torch": torch.__version__, "kornia": kornia.__version__,
            "opencv": cv2.__version__, "device": str(device),
        },
        "acceptance": config["acceptance"],
        "summary": {
            "registrations": len(results),
            "by_strategy": {
                strategy: {
                    "pairs": len([row for row in results if row["strategy"] == strategy]),
                    "accepted": sum(row["accepted"] for row in results if row["strategy"] == strategy),
                    "rejected": sum(not row["accepted"] for row in results if row["strategy"] == strategy),
                    "median_manual_corner_rmse_px": round(float(np.median([
                        row["manual_corner_rmse_px"] for row in results if row["strategy"] == strategy
                    ])), 4),
                }
                for strategy in config["match_strategies"]
            },
            "median_inference_seconds_per_pair": round(float(np.median([row["elapsed_seconds"] for row in results])), 4),
        },
        "results": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
