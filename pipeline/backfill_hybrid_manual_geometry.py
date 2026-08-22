"""Create a review-only, recording-level hybrid geometry backfill.

This intentionally does not load glyph IDs, corpus fingerprints, or cell states.
It propagates a reviewed reference lattice through an exact source video using a
direct LoFTR proposal and short-hop temporal proposals, then requires their
agreement plus independent image support.  Results are only geometry proposals:
they remain pending, have no browser overlay permission, and never modify
canonical evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from collections import defaultdict
from pathlib import Path

import cv2
import kornia
import numpy as np
import torch

from hybrid_registration_spike import (
    corner_rmse,
    diamond_check,
    fit_homography,
    fit_similarity,
    lattice_check,
    match_points,
    outside_grid,
)
from vision_registration_spike import (
    extract_frame,
    image_tensor,
    load_model,
    normalized_corners,
    project_points,
    sha256,
)


METHOD = "review-only-hybrid-loftr-direct-temporal-lattice-diamond-v1"


def manual_rows(path: Path) -> list[dict]:
    """Read exact source-video identities from evidence, never a loose source label."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if not row.get("provisional")]


def chain_frames(reference: int, targets: list[int], step: int) -> list[int]:
    """Return a monotonic reference-to-target chain in either temporal direction."""
    if not targets:
        return [reference]
    direction = 1 if all(target >= reference for target in targets) else -1
    if any((target - reference) * direction < 0 for target in targets):
        raise ValueError("Targets must be split into one directional chain")
    frames = {reference, *targets}
    cursor = reference + direction * step
    endpoint = max(targets) if direction > 0 else min(targets)
    while (cursor < endpoint) if direction > 0 else (cursor > endpoint):
        frames.add(cursor)
        cursor += direction * step
    return sorted(frames, reverse=direction < 0)


def references(config: dict) -> dict[str, dict]:
    result = {}
    for source in config.get("sources", []):
        reference_frame = int(source["reference_frame"])
        samples = {int(item["frame"]): item for item in source.get("samples", [])}
        if reference_frame not in samples:
            raise ValueError(f"{source['recording']} has no reference grid sample")
        result[source["recording"]] = {**source, "reference_sample": samples[reference_frame]}
    return result


def rounded_corners(corners: np.ndarray | None) -> list[list[float]] | None:
    return np.round(corners, 3).tolist() if corners is not None else None


def source_entry(row: dict[str, str], source_hashes: dict[str, str], reference: dict | None) -> dict:
    output = {
        "recording": row["recording"],
        "ordinal": int(row["ordinal"]),
        "frame": int(row["frame"]),
        "source_video": row["source_video"],
        "source_sha256": source_hashes.get(row["source_video"]),
        "method": METHOD,
        "review_status": "pending",
        "overlay_enabled": False,
        "reference_geometry_status": "awaiting-reviewed-reference",
        "reference_frame": None,
        "reference_geometry_provenance": None,
        "operational_consensus": False,
        "operational_status": "awaiting reviewed reference geometry",
        "proposed_grid_corners": None,
        "proposal_selected": None,
    }
    if not output["source_sha256"]:
        output["operational_status"] = "blocked: source missing from SHA-256 manifest"
    if reference:
        output.update({
            "reference_geometry_status": "reviewed-spike-seed; independent target review required",
            "reference_frame": int(reference["reference_frame"]),
            "reference_geometry_provenance": "manually-reviewed-hybrid-spike-reference-v1",
            "operational_status": "awaiting hybrid analysis from reviewed reference",
        })
    return output


def proposal_for_target(
    *, target: int, reference: dict, reference_grid: np.ndarray, paths: dict[int, Path],
    direct_pair: tuple[np.ndarray, dict], temporal_h: np.ndarray, carrier_h: np.ndarray | None, steps: list[dict], hybrid: dict,
) -> dict:
    direct_h, direct_metrics = direct_pair
    direct_grid = project_points(reference_grid, direct_h)
    temporal_grid = project_points(reference_grid, temporal_h)
    carrier_grid = project_points(reference_grid, carrier_h) if carrier_h is not None else None
    pitch = float(np.mean([
        np.linalg.norm(temporal_grid[1] - temporal_grid[0]),
        np.linalg.norm(temporal_grid[2] - temporal_grid[1]),
    ]) / 9)
    comparison = {"direct_to_all_temporal_px": corner_rmse(direct_grid, temporal_grid)}
    all_comparison = dict(comparison)
    carrier_required = bool(reference.get("carrier_temporal_required", True))
    if carrier_grid is not None:
        carrier_pairs = {
            "direct_to_carrier_temporal_px": corner_rmse(direct_grid, carrier_grid),
            "all_to_carrier_temporal_px": corner_rmse(temporal_grid, carrier_grid),
        }
        all_comparison.update(carrier_pairs)
        if carrier_required:
            comparison.update(carrier_pairs)
    disagreement_px = max(comparison.values())
    disagreement_cells = disagreement_px / max(pitch, 1e-6)
    direct_lattice = lattice_check(paths[target], direct_grid)
    temporal_lattice = lattice_check(paths[target], temporal_grid)
    carrier_lattice = (
        lattice_check(paths[target], carrier_grid) if carrier_grid is not None
        else {"usable": False, "reason": "carrier temporal chain unavailable"}
    )
    lattice_rows = [direct_lattice, temporal_lattice]
    if carrier_required:
        lattice_rows.append(carrier_lattice)
    lattice_ok = all(
        item.get("usable")
        and item["rms_residual_px"] <= hybrid["maximum_lattice_rms_px"]
        and item["weak_boundaries"] <= hybrid["maximum_weak_boundaries"]
        for item in lattice_rows
    )
    reference_diamond = np.asarray(reference["reference_diamond_corners_normalized"], dtype=np.float32) * 480
    direct_diamond = project_points(reference_diamond, direct_h)
    temporal_diamond = project_points(reference_diamond, temporal_h)
    carrier_diamond = project_points(reference_diamond, carrier_h) if carrier_h is not None else None
    if reference.get("diamond_check_enabled"):
        direct_diamond_check = diamond_check(paths[target], direct_diamond)
        temporal_diamond_check = diamond_check(paths[target], temporal_diamond)
        carrier_diamond_check = (
            diamond_check(paths[target], carrier_diamond) if carrier_diamond is not None
            else {"usable": False, "reason": "carrier temporal chain unavailable"}
        )
        diamond_rows = [direct_diamond_check, temporal_diamond_check]
        if carrier_required:
            diamond_rows.append(carrier_diamond_check)
        diamond_ok = all(
            item.get("usable")
            and item["rms_residual_px"] <= hybrid["maximum_diamond_rms_px"]
            and item["supported_sides_6px"] >= hybrid["minimum_diamond_supported_sides"]
            for item in diamond_rows
        )
    else:
        direct_diamond_check = temporal_diamond_check = carrier_diamond_check = {
            "usable": False, "reason": "disabled: reference diamond is substantially cropped"
        }
        diamond_ok = True
    minimum_inliers = min(item["all_correspondences"]["inliers"] for item in steps)
    minimum_ratio = min(item["all_correspondences"]["inlier_ratio"] for item in steps)
    consensus = (
        (not carrier_required or carrier_grid is not None)
        and disagreement_cells <= hybrid["maximum_consensus_disagreement_cells"]
        and minimum_inliers >= hybrid["minimum_temporal_step_inliers"]
        and minimum_ratio >= hybrid["minimum_temporal_step_inlier_ratio"]
        and lattice_ok and diamond_ok
    )
    if consensus:
        status = "consensus candidate; manual review required"
    elif carrier_required and carrier_grid is None:
        status = "rejected: carrier temporal chain unavailable"
    elif disagreement_cells > hybrid["maximum_consensus_disagreement_cells"]:
        status = "rejected: direct and temporal geometry disagree"
    elif not lattice_ok:
        status = "rejected: insufficient independent lattice support"
    elif not diamond_ok:
        status = "rejected: insufficient independent diamond support"
    else:
        status = "rejected: weak temporal step"
    return {
        "operational_consensus": bool(consensus), "operational_status": status,
        "proposed_grid_corners": rounded_corners(temporal_grid) if consensus else None,
        "proposal_selected": "all-feature temporal similarity chain" if consensus else None,
        "direct_grid_corners": rounded_corners(direct_grid),
        "temporal_grid_corners": rounded_corners(temporal_grid),
        "carrier_temporal_grid_corners": rounded_corners(carrier_grid),
        "direct": direct_metrics,
        "temporal_steps": steps,
        "carrier_temporal_required": carrier_required,
        "consensus_disagreement_px": round(disagreement_px, 4),
        "consensus_disagreement_cells": round(disagreement_cells, 4),
        "pairwise_disagreement": {key: round(value, 4) for key, value in comparison.items()},
        "all_pairwise_disagreement": {key: round(value, 4) for key, value in all_comparison.items()},
        "direct_lattice": direct_lattice, "temporal_lattice": temporal_lattice,
        "carrier_temporal_lattice": carrier_lattice,
        "direct_diamond": direct_diamond_check, "temporal_diamond": temporal_diamond_check,
        "carrier_temporal_diamond": carrier_diamond_check,
        "minimum_temporal_step_inliers": minimum_inliers,
        "minimum_temporal_step_inlier_ratio": minimum_ratio,
    }


def write_outputs(payload: dict, output: Path) -> None:
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rows = payload["records"]
    csv_path = output.with_suffix(".csv")
    fields = [
        "recording", "ordinal", "frame", "source_video", "source_sha256", "method", "review_status", "overlay_enabled",
        "reference_geometry_status", "reference_frame", "reference_geometry_provenance", "operational_consensus",
        "operational_status", "proposal_selected", "consensus_disagreement_cells", "minimum_temporal_step_inliers",
        "minimum_temporal_step_inlier_ratio",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    output.with_suffix(".js").write_text(
        "window.MANUAL_HYBRID_GEOMETRY_REVIEW=" + json.dumps(payload, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Backfill pending manual-frame hybrid geometry proposals.")
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=root / "pipeline" / "vision_spike_config.json")
    parser.add_argument("--output", type=Path, default=root / "data" / "manual_hybrid_geometry_review.json")
    parser.add_argument("--work-dir", type=Path, default=root / ".pipeline-work" / "hybrid-manual-backfill")
    parser.add_argument("--resume-from", type=Path, help="Merge compatible prior review-only results for recordings not in this run.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--recording", action="append", help="Only infer the named reviewed-reference recording(s).")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    hybrid = config["hybrid"]
    records = manual_rows(root / "data" / "evidence.json")
    integrity = json.loads((root / "data" / "source_integrity.json").read_text(encoding="utf-8"))
    source_hashes = {entry["filename"]: entry["sha256"] for entry in integrity["entries"]}
    reviewed = references(config)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in records:
        grouped[row["recording"]].append(row)
    output_rows = [source_entry(row, source_hashes, reviewed.get(row["recording"])) for row in records]
    output_by_key = {(row["recording"], row["ordinal"], row["frame"]): row for row in output_rows}
    if args.resume_from:
        previous = json.loads(args.resume_from.read_text(encoding="utf-8"))
        if previous.get("status") != "experimental-review-only-not-canonical" or previous.get("method") != METHOD:
            raise ValueError("Resume ledger is not a compatible review-only hybrid result")
        previous_rows = {
            (row["recording"], row["ordinal"], row["frame"]): row for row in previous.get("records", [])
        }
        for key, row in output_by_key.items():
            old = previous_rows.get(key)
            if old and (not args.recording or row["recording"] not in args.recording):
                if old.get("source_video") != row["source_video"] or old.get("source_sha256") != row["source_sha256"]:
                    raise ValueError(f"Resume source identity differs for {key}")
                row.update(old)

    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else ("cpu" if args.device == "auto" else args.device)
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but this PyTorch build cannot use it")
    device = torch.device(device_name)
    model = load_model(args.checkpoint, config["checkpoint"]["sha256"], device)
    inference_seconds = 0.0
    analysed_recordings: list[str] = []

    for recording, reference in reviewed.items():
        if args.recording and recording not in args.recording:
            continue
        source_rows = grouped.get(recording, [])
        if not source_rows:
            continue
        video = args.archive_invest / "Videos" / reference["source_video"]
        expected_hash = source_hashes.get(video.name)
        if video.name != source_rows[0]["source_video"] or not expected_hash or sha256(video) != expected_hash:
            raise RuntimeError(f"Source SHA-256 verification failed for {recording}: {video.name}")
        reference_frame = int(reference["reference_frame"])
        targets = sorted({int(row["frame"]) for row in source_rows if int(row["frame"]) != reference_frame})
        forward = [target for target in targets if target > reference_frame]
        backward = [target for target in targets if target < reference_frame]
        frame_paths: dict[int, Path] = {}
        tensors: dict[int, torch.Tensor] = {}
        frames_dir = args.work_dir / "frames" / recording

        def tensor_for(frame: int) -> torch.Tensor:
            if frame not in frame_paths:
                destination = frames_dir / f"f{frame:06d}.png"
                extract_frame(args.ffmpeg, video, frame, 480, destination)
                frame_paths[frame] = destination
            if frame not in tensors:
                tensors[frame] = image_tensor(frame_paths[frame], device)
            return tensors[frame]

        reference_grid = normalized_corners(reference["reference_sample"], 480)
        tensor_for(reference_frame)
        per_target: dict[int, dict] = {}
        seed_row = next((row for row in source_rows if int(row["frame"]) == reference_frame), None)
        if seed_row:
            target = output_by_key[(recording, seed_row["ordinal"], seed_row["frame"])]
            target.update({
                "operational_status": "reviewed reference seed; independent target review still required",
                "proposed_grid_corners": rounded_corners(reference_grid),
                "proposal_selected": "reviewed reference seed",
            })

        def propagate_step(
            prior: int, current: int, cumulative: np.ndarray, cumulative_carrier: np.ndarray,
            carrier_available: bool, accumulated: list[dict],
        ) -> tuple[np.ndarray, np.ndarray, bool, list[dict]]:
            """Use one short hop; target hops never become anchors for later targets."""
            nonlocal inference_seconds
            points0, points1, elapsed = match_points(model, tensor_for(prior), tensor_for(current))
            inference_seconds += elapsed
            step_h, step_metrics = fit_similarity(points0, points1)
            carrier_h, carrier_metrics = None, {"available": False, "reason": "carrier chain already unavailable"}
            if carrier_available:
                selected = outside_grid(points0, project_points(reference_grid, cumulative_carrier))
                if int(selected.sum()) >= 4:
                    try:
                        carrier_h, carrier_metrics = fit_similarity(points0[selected], points1[selected])
                        carrier_metrics["available"] = True
                    except RuntimeError as error:
                        carrier_metrics = {"available": False, "reason": str(error), "matches": int(selected.sum())}
                else:
                    carrier_metrics = {"available": False, "reason": "fewer than four carrier matches", "matches": int(selected.sum())}
                if carrier_h is None:
                    carrier_available = False
            next_cumulative = step_h @ cumulative
            next_carrier = carrier_h @ cumulative_carrier if carrier_h is not None else cumulative_carrier
            return next_cumulative, next_carrier, carrier_available, accumulated + [{
                "from_frame": prior, "to_frame": current, "elapsed_seconds": round(elapsed, 4),
                "all_correspondences": step_metrics, "carrier_only": carrier_metrics,
            }]

        for direction_targets in (forward, backward):
            if not direction_targets:
                continue
            direction = 1 if direction_targets is forward else -1
            endpoint = max(direction_targets) if direction > 0 else min(direction_targets)
            anchors = [reference_frame]
            while (anchors[-1] + direction * int(hybrid["temporal_step_frames"]) < endpoint) if direction > 0 else (anchors[-1] + direction * int(hybrid["temporal_step_frames"]) > endpoint):
                anchors.append(anchors[-1] + direction * int(hybrid["temporal_step_frames"]))
            anchor_states = {
                reference_frame: (np.eye(3, dtype=np.float64), np.eye(3, dtype=np.float64), True, [])
            }
            for prior, current in zip(anchors, anchors[1:]):
                anchor_states[current] = propagate_step(prior, current, *anchor_states[prior])
            for target in direction_targets:
                anchor = max((frame for frame in anchors if frame <= target), default=reference_frame) if direction > 0 else min((frame for frame in anchors if frame >= target), default=reference_frame)
                cumulative, cumulative_carrier, carrier_available, steps = anchor_states[anchor]
                if target != anchor:
                    cumulative, cumulative_carrier, carrier_available, steps = propagate_step(
                        anchor, target, cumulative, cumulative_carrier, carrier_available, steps
                    )
                points0, points1, elapsed = match_points(model, tensor_for(reference_frame), tensor_for(target))
                inference_seconds += elapsed
                direct_h, direct_metrics = fit_homography(points0, points1)
                per_target[target] = proposal_for_target(
                    target=target, reference=reference, reference_grid=reference_grid, paths=frame_paths,
                    direct_pair=(direct_h, direct_metrics), temporal_h=cumulative,
                    carrier_h=cumulative_carrier if carrier_available else None,
                    steps=steps, hybrid=hybrid,
                )
        for source_row in source_rows:
            frame = int(source_row["frame"])
            if frame == reference_frame:
                continue
            output_by_key[(recording, source_row["ordinal"], source_row["frame"])].update(per_target.get(frame, {
                "operational_status": "rejected: registration did not produce a proposal"
            }))
        analysed_recordings.append(recording)
        print(json.dumps({"recording": recording, "manual_frames": len(source_rows), "analysed": len(per_target)}))

    candidates = [row for row in output_rows if row.get("operational_consensus")]
    analysed_recordings = sorted({
        row["recording"] for row in output_rows
        if row.get("operational_status", "").startswith(("consensus candidate", "rejected:", "reviewed reference seed"))
    })
    payload = {
        "schema_version": 1,
        "status": "experimental-review-only-not-canonical",
        "method": METHOD,
        "warning": "No row enables an overlay or changes evidence. Corpus fingerprints, glyph IDs, and cell values are never loaded.",
        "checkpoint": {**config["checkpoint"], "local_sha256_verified": True},
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "kornia": kornia.__version__, "opencv": cv2.__version__, "device": str(device)},
        "hybrid_thresholds": hybrid,
        "summary": {
            "manual_occurrences": len(output_rows), "recordings": len(grouped), "reviewed_reference_recordings": len(reviewed),
            "analysed_recordings": analysed_recordings, "analysed_occurrences": sum(row["recording"] in analysed_recordings for row in output_rows),
            "awaiting_reviewed_reference": sum(row["reference_frame"] is None for row in output_rows),
            "awaiting_hybrid_analysis": sum(row.get("operational_status") == "awaiting hybrid analysis from reviewed reference" for row in output_rows),
            "operational_candidates": len(candidates), "operational_rejections": sum(
                row.get("operational_status", "").startswith("rejected:") for row in output_rows
            ), "reference_seed_rows": sum(
                row.get("operational_status", "").startswith("reviewed reference seed") for row in output_rows
            ), "total_inference_seconds": round(inference_seconds, 4),
        },
        "records": output_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_outputs(payload, args.output)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
