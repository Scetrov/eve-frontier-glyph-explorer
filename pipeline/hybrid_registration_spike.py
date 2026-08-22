"""Test conservative LoFTR + temporal + lattice registration consensus.

This is an experimental review producer. It never loads glyph IDs, corpus
fingerprints, or cell states and cannot publish evidence overlay coordinates.
Manual target corners are used only after registration to score the experiment.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import cv2
import kornia
import numpy as np
import torch

from vision_registration_spike import (
    MARTIAN_RED,
    NEUTRAL,
    dashed_line,
    extract_frame,
    grid_segments,
    image_tensor,
    load_model,
    normalized_corners,
    project_points,
    reprojection_errors,
    sha256,
)


TEMPORAL = (255, 190, 70)
TEMPORAL_CARRIER = (200, 90, 220)
DIM = (104, 104, 100)


def match_points(model, image0: torch.Tensor, image1: torch.Tensor) -> tuple[np.ndarray, np.ndarray, float]:
    started = time.perf_counter()
    with torch.inference_mode():
        match = model({"image0": image0, "image1": image1})
    return (
        match["keypoints0"].detach().cpu().numpy().astype(np.float32),
        match["keypoints1"].detach().cpu().numpy().astype(np.float32),
        time.perf_counter() - started,
    )


def fit_homography(points0: np.ndarray, points1: np.ndarray) -> tuple[np.ndarray, dict]:
    homography, mask = cv2.findHomography(
        points0, points1, cv2.USAC_MAGSAC, 2.5, maxIters=10000, confidence=0.999
    )
    if homography is None or mask is None:
        raise RuntimeError("Homography estimation failed")
    inliers = mask.ravel().astype(bool)
    errors = reprojection_errors(points0[inliers], points1[inliers], homography)
    return homography, {
        "matches": int(len(points0)),
        "inliers": int(inliers.sum()),
        "inlier_ratio": round(float(inliers.mean()), 4),
        "median_reprojection_error_px": round(float(np.median(errors)), 4),
    }


def fit_similarity(points0: np.ndarray, points1: np.ndarray) -> tuple[np.ndarray, dict]:
    affine, mask = cv2.estimateAffinePartial2D(
        points0, points1, method=cv2.RANSAC, ransacReprojThreshold=2.5,
        maxIters=10000, confidence=0.999, refineIters=10,
    )
    if affine is None or mask is None:
        raise RuntimeError("Similarity estimation failed")
    homography = np.vstack((affine, [0.0, 0.0, 1.0]))
    inliers = mask.ravel().astype(bool)
    errors = reprojection_errors(points0[inliers], points1[inliers], homography)
    return homography, {
        "matches": int(len(points0)),
        "inliers": int(inliers.sum()),
        "inlier_ratio": round(float(inliers.mean()), 4),
        "median_reprojection_error_px": round(float(np.median(errors)), 4),
    }


def chain_frames(reference: int, targets: list[int], step: int) -> list[int]:
    if any(target <= reference for target in targets):
        raise ValueError("The current spike expects target frames after the reference")
    frames = {reference, *targets}
    cursor = reference + step
    while cursor < max(targets):
        frames.add(cursor)
        cursor += step
    return sorted(frames)


def lattice_check(image_path: Path, corners: np.ndarray) -> dict:
    """Measure whether all ten proposed row/column boundaries have nearby edge support."""
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Could not read {image_path}")
    height, width = gray.shape
    left = float((corners[0, 0] + corners[3, 0]) / 2)
    right = float((corners[1, 0] + corners[2, 0]) / 2)
    top = float((corners[0, 1] + corners[1, 1]) / 2)
    bottom = float((corners[2, 1] + corners[3, 1]) / 2)
    pitch_x, pitch_y = (right - left) / 9, (bottom - top) / 9
    y0, y1 = max(0, int(round(top))), min(height, int(round(bottom)))
    x0, x1 = max(0, int(round(left))), min(width, int(round(right)))
    if y1 - y0 < 32 or x1 - x0 < 32 or pitch_x < 8 or pitch_y < 8:
        return {"usable": False, "reason": "projected grid has insufficient visible area"}

    edge_x = np.abs(cv2.Sobel(gray[y0:y1], cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    edge_y = np.abs(cv2.Sobel(gray[:, x0:x1], cv2.CV_32F, 0, 1, ksize=3)).mean(axis=1)

    def measure(projection: np.ndarray, positions: np.ndarray, pitch: float) -> tuple[list[float], list[float]]:
        residuals, strengths = [], []
        radius = max(2, int(round(abs(pitch) * 0.18)))
        baseline = float(np.median(projection) + 1e-6)
        for position in positions:
            center = int(round(float(position)))
            if center < 0 or center >= len(projection):
                continue
            low, high = max(0, center - radius), min(len(projection), center + radius + 1)
            local = projection[low:high]
            peak = low + int(np.argmax(local))
            residuals.append(float(abs(peak - position)))
            strengths.append(float(projection[peak] / baseline))
        return residuals, strengths

    residual_x, strength_x = measure(edge_x, np.linspace(left, right, 10), pitch_x)
    residual_y, strength_y = measure(edge_y, np.linspace(top, bottom, 10), pitch_y)
    residuals, strengths = residual_x + residual_y, strength_x + strength_y
    if len(residuals) < 12:
        return {"usable": False, "reason": "fewer than twelve visible lattice boundaries"}
    return {
        "usable": True,
        "visible_boundaries": len(residuals),
        "rms_residual_px": round(float(np.sqrt(np.mean(np.square(residuals)))), 4),
        "median_strength_ratio": round(float(np.median(strengths)), 4),
        "weak_boundaries": int(sum(value < 1.5 for value in strengths)),
        "pitch_x_px": round(float(pitch_x), 4),
        "pitch_y_px": round(float(pitch_y), 4),
    }


def diamond_check(image_path: Path, corners: np.ndarray) -> dict:
    """Score projected diamond sides against long diagonal Hough evidence."""
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Could not read {image_path}")
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
    detected = cv2.HoughLines(edges, 1, np.pi / 720, 90)
    if detected is None:
        return {"usable": False, "reason": "no diagonal Hough lines"}
    lines = detected[:, 0]
    distances = []
    for index in range(4):
        start, end = corners[index], corners[(index + 1) % 4]
        direction = end - start
        side_angle = float(np.arctan2(direction[1], direction[0]) % np.pi)
        candidates = []
        for rho, theta in lines:
            line_angle = float((theta + np.pi / 2) % np.pi)
            angle_delta = abs(line_angle - side_angle)
            angle_delta = min(angle_delta, np.pi - angle_delta)
            if angle_delta > np.deg2rad(3.0):
                continue
            normal = np.asarray([np.cos(theta), np.sin(theta)], dtype=np.float32)
            distance = float(np.mean(np.abs(np.asarray([start, end]) @ normal - rho)))
            candidates.append(distance)
        distances.append(min(candidates) if candidates else float("inf"))
    finite = [value for value in distances if np.isfinite(value)]
    if len(finite) < 3:
        return {"usable": False, "reason": "fewer than three diamond sides have directional support"}
    return {
        "usable": True,
        "side_residuals_px": [round(value, 4) if np.isfinite(value) else None for value in distances],
        "rms_residual_px": round(float(np.sqrt(np.mean(np.square(finite)))), 4),
        "supported_sides_6px": int(sum(value <= 6.0 for value in finite)),
        "hough_lines": int(len(lines)),
    }


def corner_rmse(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum((left - right) ** 2, axis=1))))


def outside_grid(points: np.ndarray, corners: np.ndarray) -> np.ndarray:
    left, top = corners.min(axis=0)
    right, bottom = corners.max(axis=0)
    return ((points[:, 0] < left) | (points[:, 0] > right)
            | (points[:, 1] < top) | (points[:, 1] > bottom))


def draw_grid(image: np.ndarray, corners: np.ndarray, color: tuple[int, int, int], dotted: bool = False) -> None:
    for start, end in grid_segments(corners):
        if dotted:
            dashed_line(image, start, end, color)
        else:
            cv2.line(image, tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int)),
                     color, 1, cv2.LINE_AA)


def render(
    image_path: Path,
    direct: np.ndarray,
    temporal: np.ndarray,
    temporal_carrier: np.ndarray | None,
    manual: np.ndarray,
    metrics: dict,
    output: Path,
) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    draw_grid(image, direct, MARTIAN_RED)
    draw_grid(image, temporal, TEMPORAL, dotted=True)
    if temporal_carrier is not None:
        draw_grid(image, temporal_carrier, TEMPORAL_CARRIER, dotted=True)
    for index in range(4):
        dashed_line(image, manual[index], manual[(index + 1) % 4], NEUTRAL)
    header = np.full((88, image.shape[1], 3), (11, 11, 11), dtype=np.uint8)
    title = f"{metrics['recording']} / {metrics['reference_frame']} -> {metrics['target_frame']} / HYBRID"
    cv2.putText(header, title, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.44, NEUTRAL, 1, cv2.LINE_AA)
    line = (
        f"max proposal spread {metrics['consensus_disagreement_cells']:.3f} cells / "
        f"best proposal RMSE {metrics['evaluation']['best_proposal_corner_rmse_px']:.2f}px"
    )
    cv2.putText(header, line, (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.35, MARTIAN_RED, 1, cv2.LINE_AA)
    cv2.putText(header, metrics["operational_status"].upper(), (12, 66),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, TEMPORAL, 1, cv2.LINE_AA)
    cv2.putText(header, "orange direct / cyan all-temporal / violet carrier-temporal / pale manual", (12, 82),
                cv2.FONT_HERSHEY_SIMPLEX, 0.25, NEUTRAL, 1, cv2.LINE_AA)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), np.vstack((header, image)), [cv2.IMWRITE_JPEG_QUALITY, 92])


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the conservative hybrid registration spike.")
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=root / "pipeline" / "vision_spike_config.json")
    parser.add_argument("--output-dir", type=Path, default=root / ".pipeline-work" / "hybrid-vision-spike" / "run")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--recording", action="append", help="Limit the run to one or more recording labels")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    hybrid = config["hybrid"]
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
    results, total_inference_seconds = [], 0.0

    for source in config["sources"]:
        if args.recording and source["recording"] not in args.recording:
            continue
        base = args.archive_invest / "Videos" if source["location"] == "archive-invest" else args.video_dir
        video = base / source["source_video"]
        expected_hash = source_hashes.get(video.name)
        if expected_hash is None or sha256(video) != expected_hash:
            raise RuntimeError(f"Source SHA-256 verification failed for {video.name}")
        samples = {int(row["frame"]): row for row in source["samples"]}
        reference_frame = int(source["reference_frame"])
        targets = sorted(frame for frame in samples if frame != reference_frame)
        frames = chain_frames(reference_frame, targets, int(hybrid["temporal_step_frames"]))
        paths, tensors = {}, {}

        def tensor_for(frame: int) -> torch.Tensor:
            if frame not in paths:
                path = frame_dir / f"{source['recording']}_f{frame:06d}.png"
                extract_frame(args.ffmpeg, video, frame, image_size, path)
                paths[frame] = path
            if frame not in tensors:
                tensors[frame] = image_tensor(paths[frame], device)
            return tensors[frame]

        reference_grid = normalized_corners(samples[reference_frame], image_size)
        cumulative = np.eye(3, dtype=np.float64)
        cumulative_carrier = np.eye(3, dtype=np.float64)
        carrier_chain_available = True
        temporal_by_frame, carrier_temporal_by_frame, steps_by_frame, prior = {}, {}, {}, reference_frame
        accumulated_steps = []
        tensor_for(reference_frame)
        for current in frames[1:]:
            points0, points1, elapsed = match_points(model, tensor_for(prior), tensor_for(current))
            total_inference_seconds += elapsed
            step_h, step_metrics = fit_similarity(points0, points1)
            carrier_metrics = {"available": False, "reason": "carrier chain already unavailable"}
            carrier_h = None
            if carrier_chain_available:
                carrier_grid_before = project_points(reference_grid, cumulative_carrier)
                selected = outside_grid(points0, carrier_grid_before)
                if int(selected.sum()) >= 4:
                    try:
                        carrier_h, carrier_metrics = fit_similarity(points0[selected], points1[selected])
                        carrier_metrics["available"] = True
                    except RuntimeError as error:
                        carrier_metrics = {"available": False, "reason": str(error), "matches": int(selected.sum())}
                else:
                    carrier_metrics = {
                        "available": False, "reason": "fewer than four carrier matches",
                        "matches": int(selected.sum()),
                    }
                if carrier_h is None:
                    carrier_chain_available = False
            accumulated_steps.append({
                "from_frame": prior, "to_frame": current, "elapsed_seconds": round(elapsed, 4),
                "all_correspondences": step_metrics, "carrier_only": carrier_metrics,
            })
            cumulative = step_h @ cumulative
            if carrier_h is not None:
                cumulative_carrier = carrier_h @ cumulative_carrier
            if current in targets:
                temporal_by_frame[current] = cumulative.copy()
                carrier_temporal_by_frame[current] = cumulative_carrier.copy() if carrier_chain_available else None
                steps_by_frame[current] = list(accumulated_steps)
            prior = current

        for target in targets:
            points0, points1, elapsed = match_points(model, tensor_for(reference_frame), tensor_for(target))
            total_inference_seconds += elapsed
            direct_h, direct_metrics = fit_homography(points0, points1)
            direct_grid = project_points(reference_grid, direct_h)
            temporal_grid = project_points(reference_grid, temporal_by_frame[target])
            carrier_h = carrier_temporal_by_frame[target]
            carrier_temporal_grid = project_points(reference_grid, carrier_h) if carrier_h is not None else None
            manual_grid = normalized_corners(samples[target], image_size)
            target_pitch = float(np.mean([
                np.linalg.norm(temporal_grid[1] - temporal_grid[0]),
                np.linalg.norm(temporal_grid[2] - temporal_grid[1]),
            ]) / 9)
            disagreement_pairs = {
                "direct_to_all_temporal_px": corner_rmse(direct_grid, temporal_grid),
            }
            carrier_temporal_required = bool(source.get("carrier_temporal_required", True))
            if carrier_temporal_grid is not None:
                carrier_disagreement_pairs = {
                    "direct_to_carrier_temporal_px": corner_rmse(direct_grid, carrier_temporal_grid),
                    "all_to_carrier_temporal_px": corner_rmse(temporal_grid, carrier_temporal_grid),
                }
            else:
                carrier_disagreement_pairs = {}
            all_disagreement_pairs = {**disagreement_pairs, **carrier_disagreement_pairs}
            if carrier_temporal_required:
                disagreement_pairs.update(carrier_disagreement_pairs)
            disagreement_px = max(disagreement_pairs.values())
            disagreement_cells = disagreement_px / max(target_pitch, 1e-6)
            direct_lattice = lattice_check(paths[target], direct_grid)
            temporal_lattice = lattice_check(paths[target], temporal_grid)
            carrier_temporal_lattice = (
                lattice_check(paths[target], carrier_temporal_grid) if carrier_temporal_grid is not None
                else {"usable": False, "reason": "carrier temporal chain unavailable"}
            )
            step_rows = steps_by_frame[target]
            minimum_step_inliers = min(
                row["all_correspondences"]["inliers"] for row in step_rows
            )
            minimum_step_ratio = min(
                row["all_correspondences"]["inlier_ratio"] for row in step_rows
            )
            line_ok = (
                direct_lattice.get("usable") and temporal_lattice.get("usable")
                and direct_lattice["rms_residual_px"] <= hybrid["maximum_lattice_rms_px"]
                and temporal_lattice["rms_residual_px"] <= hybrid["maximum_lattice_rms_px"]
                and direct_lattice["weak_boundaries"] <= hybrid["maximum_weak_boundaries"]
                and temporal_lattice["weak_boundaries"] <= hybrid["maximum_weak_boundaries"]
            )
            if carrier_temporal_required:
                line_ok = (
                    line_ok and carrier_temporal_lattice.get("usable")
                    and carrier_temporal_lattice["rms_residual_px"] <= hybrid["maximum_lattice_rms_px"]
                    and carrier_temporal_lattice["weak_boundaries"] <= hybrid["maximum_weak_boundaries"]
                )
            reference_diamond = (
                np.asarray(source["reference_diamond_corners_normalized"], dtype=np.float32) * image_size
            )
            direct_diamond = project_points(reference_diamond, direct_h)
            temporal_diamond = project_points(reference_diamond, temporal_by_frame[target])
            carrier_temporal_diamond = (
                project_points(reference_diamond, carrier_h) if carrier_h is not None else None
            )
            if source.get("diamond_check_enabled"):
                direct_diamond_check = diamond_check(paths[target], direct_diamond)
                temporal_diamond_check = diamond_check(paths[target], temporal_diamond)
                carrier_diamond_check = (
                    diamond_check(paths[target], carrier_temporal_diamond)
                    if carrier_temporal_diamond is not None
                    else {"usable": False, "reason": "carrier temporal chain unavailable"}
                )
                diamond_rows = [direct_diamond_check, temporal_diamond_check]
                if carrier_temporal_required:
                    diamond_rows.append(carrier_diamond_check)
                diamond_ok = all(
                    row.get("usable")
                    and row["rms_residual_px"] <= hybrid["maximum_diamond_rms_px"]
                    and row["supported_sides_6px"] >= hybrid["minimum_diamond_supported_sides"]
                    for row in diamond_rows
                )
            else:
                direct_diamond_check = temporal_diamond_check = carrier_diamond_check = {
                    "usable": False, "reason": "disabled: reference diamond is substantially cropped"
                }
                diamond_ok = True
            consensus = (
                (not carrier_temporal_required or carrier_temporal_grid is not None)
                and disagreement_cells <= hybrid["maximum_consensus_disagreement_cells"]
                and minimum_step_inliers >= hybrid["minimum_temporal_step_inliers"]
                and minimum_step_ratio >= hybrid["minimum_temporal_step_inlier_ratio"]
                and line_ok
                and diamond_ok
            )
            evaluation = {
                "direct_corner_rmse_px": round(corner_rmse(direct_grid, manual_grid), 4),
                "temporal_corner_rmse_px": round(corner_rmse(temporal_grid, manual_grid), 4),
                "carrier_temporal_corner_rmse_px": (
                    round(corner_rmse(carrier_temporal_grid, manual_grid), 4)
                    if carrier_temporal_grid is not None else None
                ),
            }
            proposal_errors = [evaluation["direct_corner_rmse_px"], evaluation["temporal_corner_rmse_px"]]
            if evaluation["carrier_temporal_corner_rmse_px"] is not None:
                proposal_errors.append(evaluation["carrier_temporal_corner_rmse_px"])
            evaluation["best_proposal_corner_rmse_px"] = min(proposal_errors)
            evaluation["geometry_correct"] = (
                evaluation["best_proposal_corner_rmse_px"] <= config["acceptance"]["maximum_manual_corner_rmse_px"]
            )
            if consensus:
                operational_status = "consensus candidate; manual review required"
            elif carrier_temporal_required and carrier_temporal_grid is None:
                operational_status = "rejected: carrier temporal chain unavailable"
            elif disagreement_cells > hybrid["maximum_consensus_disagreement_cells"]:
                operational_status = "rejected: direct and temporal geometry disagree"
            elif not line_ok:
                operational_status = "rejected: insufficient independent lattice support"
            elif not diamond_ok:
                operational_status = "rejected: insufficient independent diamond support"
            else:
                operational_status = "rejected: weak temporal step"
            result = {
                "recording": source["recording"], "source_video": video.name, "source_sha256": expected_hash,
                "reference_frame": reference_frame, "target_frame": target,
                "direct": direct_metrics, "temporal_steps": step_rows,
                "direct_grid_corners": np.round(direct_grid, 3).tolist(),
                "temporal_grid_corners": np.round(temporal_grid, 3).tolist(),
                "carrier_temporal_grid_corners": (
                    np.round(carrier_temporal_grid, 3).tolist() if carrier_temporal_grid is not None else None
                ),
                "manual_grid_corners": np.round(manual_grid, 3).tolist(),
                "consensus_disagreement_px": round(disagreement_px, 4),
                "consensus_disagreement_cells": round(disagreement_cells, 4),
                "pairwise_disagreement": {key: round(value, 4) for key, value in disagreement_pairs.items()},
                "all_pairwise_disagreement": {
                    key: round(value, 4) for key, value in all_disagreement_pairs.items()
                },
                "carrier_temporal_required": carrier_temporal_required,
                "direct_lattice": direct_lattice, "temporal_lattice": temporal_lattice,
                "carrier_temporal_lattice": carrier_temporal_lattice,
                "direct_diamond": direct_diamond_check,
                "temporal_diamond": temporal_diamond_check,
                "carrier_temporal_diamond": carrier_diamond_check,
                "minimum_temporal_step_inliers": minimum_step_inliers,
                "minimum_temporal_step_inlier_ratio": minimum_step_ratio,
                "operational_consensus": bool(consensus), "operational_status": operational_status,
                "evaluation": evaluation,
            }
            render_name = f"{source['recording']}_f{reference_frame:06d}_to_f{target:06d}_hybrid.jpg"
            result["render"] = f"renders/{render_name}"
            render(paths[target], direct_grid, temporal_grid, carrier_temporal_grid,
                   manual_grid, result, render_dir / render_name)
            results.append(result)
            print(json.dumps({key: result[key] for key in (
                "recording", "target_frame", "consensus_disagreement_cells",
                "operational_consensus", "operational_status"
            )}))

    candidates = [row for row in results if row["operational_consensus"]]
    payload = {
        "schema_version": 1,
        "status": "experimental-not-canonical",
        "method": "direct-loftr-homography-plus-all-and-carrier-temporal-chains-plus-lattice-and-diamond-consensus",
        "geometry_labels": "manual target corners used only for post-registration evaluation; no glyph or cell data loaded",
        "checkpoint": {**config["checkpoint"], "local_sha256_verified": True},
        "environment": {
            "python": platform.python_version(), "torch": torch.__version__, "kornia": kornia.__version__,
            "opencv": cv2.__version__, "device": str(device),
        },
        "hybrid_thresholds": hybrid,
        "summary": {
            "pairs": len(results), "operational_candidates": len(candidates),
            "operational_rejections": len(results) - len(candidates),
            "false_positive_candidates": sum(not row["evaluation"]["geometry_correct"] for row in candidates),
            "correct_geometry_candidates": sum(row["evaluation"]["geometry_correct"] for row in candidates),
            "correct_geometry_rejected": sum(
                row["evaluation"]["geometry_correct"] and not row["operational_consensus"] for row in results
            ),
            "total_inference_seconds": round(total_inference_seconds, 4),
        },
        "results": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
