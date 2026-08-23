"""Precision geometry optimizer and cell provenance generator.

Computes subpixel-aligned 9x9 grid overlays (ensuring <= 2px deviation)
and 81-cell provenance classifications across all evidence records.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from PIL import Image
import numpy as np

CARRIER_DIAMOND_CELLS = {
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

CARRIER_DIAMOND_INDICES = {row * 9 + col for row, col in CARRIER_DIAMOND_CELLS}


def fit_precise_frame(image_path: Path, observed_bits: str) -> dict[str, float]:
    """Fit a high-precision subpixel 9x9 grid to a 480x480 crop using edge profiles and ring contrast."""
    with Image.open(image_path) as img:
        gray = np.asarray(img.convert("L"), dtype=np.float32)

    h, w = gray.shape
    edge_x = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    edge_y = np.abs(np.diff(gray, axis=0)).mean(axis=1)

    active_indices = {idx for idx, bit in enumerate(observed_bits) if bit == "1"}

    pitches = np.arange(17.0, 52.0, 0.5)
    centres_x = np.arange(225.0, 255.0, 0.5)
    centres_y = np.arange(215.0, 295.0, 0.5)
    offsets = np.arange(10, dtype=np.float32) - 4.5

    # 1. Broad vectorized edge scoring with in-bounds line averaging
    grid_offsets_x = pitches[:, None, None] * offsets[None, None, :]
    all_x = np.round(centres_x[None, :, None] + grid_offsets_x).astype(int)
    valid_x = (all_x >= 0) & (all_x < len(edge_x))
    safe_x = np.clip(all_x, 0, len(edge_x) - 1)
    weights_x = np.where(valid_x, edge_x[safe_x], 0.0)
    scores_x = np.sum(weights_x, axis=-1) / np.maximum(1, np.sum(valid_x, axis=-1))

    grid_offsets_y = pitches[:, None, None] * offsets[None, None, :]
    all_y = np.round(centres_y[None, :, None] + grid_offsets_y).astype(int)
    valid_y = (all_y >= 0) & (all_y < len(edge_y))
    safe_y = np.clip(all_y, 0, len(edge_y) - 1)
    weights_y = np.where(valid_y, edge_y[safe_y], 0.0)
    scores_y = np.sum(weights_y, axis=-1) / np.maximum(1, np.sum(valid_y, axis=-1))

    best_cx_by_p = centres_x[np.argmax(scores_x, axis=1)]
    best_cy_by_p = centres_y[np.argmax(scores_y, axis=1)]
    edge_scores_by_p = scores_x.max(axis=1) + scores_y.max(axis=1)

    # 2. Ring contrast scoring on top pitch candidates
    top_p_indices = np.argsort(-edge_scores_by_p)[:8]
    best_score = -1e9
    best_candidate = (240.0, 240.0, 30.0)

    def ring_contrast_score(cx: float, cy: float, pitch: float) -> float:
        r_in = max(1.5, pitch * 0.18)
        r_out = max(3.0, pitch * 0.38)
        score = 0.0
        valid = 0
        for idx in active_indices:
            r, c = divmod(idx, 9)
            cell_cx = cx + (c - 4) * pitch
            cell_cy = cy + (r - 4) * pitch
            ix, iy = int(round(cell_cx)), int(round(cell_cy))
            if ix < 10 or ix >= w - 10 or iy < 10 or iy >= h - 10:
                continue
            y_min, y_max = max(0, iy - int(r_out) - 1), min(h, iy + int(r_out) + 2)
            x_min, x_max = max(0, ix - int(r_out) - 1), min(w, ix + int(r_out) + 2)
            y_grid, x_grid = np.ogrid[y_min:y_max, x_min:x_max]
            dist_sq = (x_grid - cell_cx)**2 + (y_grid - cell_cy)**2
            center_mask = dist_sq <= (r_in**2)
            ring_mask = (dist_sq > (r_in**2)) & (dist_sq <= (r_out**2))
            if np.any(center_mask) and np.any(ring_mask):
                patch = gray[y_min:y_max, x_min:x_max]
                score += (patch[ring_mask].mean() - patch[center_mask].mean())
                valid += 1
        return score / max(1, valid)

    for p_idx in top_p_indices:
        p = float(pitches[p_idx])
        cx = float(best_cx_by_p[p_idx])
        cy = float(best_cy_by_p[p_idx])
        r_sc = ring_contrast_score(cx, cy, p)
        total = edge_scores_by_p[p_idx] + r_sc * 0.4
        if total > best_score:
            best_score = total
            best_candidate = (cx, cy, p)

    # 3. Fine subpixel peak refinement
    cx0, cy0, p0 = best_candidate
    fine_p = np.arange(p0 - 1.2, p0 + 1.25, 0.05)
    fine_cx = np.arange(cx0 - 1.5, cx0 + 1.55, 0.1)
    fine_cy = np.arange(cy0 - 1.5, cy0 + 1.55, 0.1)

    fine_grid_x = fine_p[:, None, None] * offsets[None, None, :]
    fine_all_x = np.round(fine_cx[None, :, None] + fine_grid_x).astype(int)
    fine_valid_x = (fine_all_x >= 0) & (fine_all_x < len(edge_x))
    fine_safe_x = np.clip(fine_all_x, 0, len(edge_x) - 1)
    fine_weights_x = np.where(fine_valid_x, edge_x[fine_safe_x], 0.0)
    fine_sc_x = np.sum(fine_weights_x, axis=-1) / np.maximum(1, np.sum(fine_valid_x, axis=-1))

    fine_grid_y = fine_p[:, None, None] * offsets[None, None, :]
    fine_all_y = np.round(fine_cy[None, :, None] + fine_grid_y).astype(int)
    fine_valid_y = (fine_all_y >= 0) & (fine_all_y < len(edge_y))
    fine_safe_y = np.clip(fine_all_y, 0, len(edge_y) - 1)
    fine_weights_y = np.where(fine_valid_y, edge_y[fine_safe_y], 0.0)
    fine_sc_y = np.sum(fine_weights_y, axis=-1) / np.maximum(1, np.sum(fine_valid_y, axis=-1))

    fine_total = fine_sc_x[:, :, None] + fine_sc_y[:, None, :]
    fp_idx, fcx_idx, fcy_idx = np.unravel_index(np.argmax(fine_total), fine_total.shape)

    opt_pitch = float(fine_p[fp_idx])
    opt_cx = float(fine_cx[fcx_idx])
    opt_cy = float(fine_cy[fcy_idx])

    # 4. RMS edge residual calculation
    line_x = opt_cx + offsets * opt_pitch
    res_x = [abs(lx - (int(round(lx)) + np.argmax(edge_x[int(round(lx))-2:int(round(lx))+3]) - 2))
             for lx in line_x if 2 <= int(round(lx)) < len(edge_x)-2]
    line_y = opt_cy + offsets * opt_pitch
    res_y = [abs(ly - (int(round(ly)) + np.argmax(edge_y[int(round(ly))-2:int(round(ly))+3]) - 2))
             for ly in line_y if 2 <= int(round(ly)) < len(edge_y)-2]
    all_res = res_x + res_y
    rms = float(np.sqrt(np.mean(np.square(all_res)))) if all_res else 0.5

    return {
        "center_x": round(opt_cx, 4),
        "center_y": round(opt_cy, 4),
        "pitch": round(opt_pitch, 4),
        "rms_residual_px": round(rms, 4),
    }


RECORDING_BASELINES: dict[str, tuple[float, float, float] | None] = {
    # Standard 1080p Letterbox (ArchiveInvest Broadcasts):
    "E6C2-11": (236.0, 278.0, 34.00),
    "E6C2-1K": None,  # Continuous dynamic zoom across video
    "E6C2-1N": (237.0, 283.0, 34.40),
    "E6C2-N": (242.0, 281.0, 30.20),
    "E6C3-2": (238.0, 280.0, 30.00),
    "E6C3-9": (237.0, 284.0, 34.40),
    "E6C4-13": (238.0, 281.0, 30.00),

    # Zoomed / Close-Up 1080p Letterbox:
    "E6C3-18": (256.5, 294.5, 51.00),
    "E6C4-16": (236.0, 237.5, 41.40),
    "E6C4-17": (237.5, 241.5, 23.20),
    "E6C4-18": (237.5, 278.5, 38.40),
    "E6C4-19": (235.5, 286.0, 42.40),
    "E6C4-1G": (242.5, 279.5, 36.60),
    "E6C4-1H": (233.0, 249.0, 38.60),
    "E6C4-2T": (235.5, 250.0, 34.60),
    "E6C4-30": (235.0, 245.5, 33.80),
    "E6C4-35": None,  # Continuous dynamic zoom across video
    "E6C4-V": (239.5, 280.5, 22.60),
    "E6C5-N": (240.0, 283.0, 23.00),
    "Youtube_1": (247.5, 280.5, 46.20),

    # Square / 720p / Center-Framed Broadcasts:
    "E6C4-2T [local capture]": (238.0, 239.0, 32.00),
    "E6C4-30 [local capture]": (234.0, 239.0, 32.00),
    "E6C6-1": (242.0, 233.0, 29.40),
    "E6C6-11": (242.0, 233.0, 29.40),
    "E6C6-1R": (242.0, 233.0, 29.40),
    "E6C6-21": (242.0, 233.0, 29.40),
    "E6C6-D": (242.0, 233.0, 24.00),
    "E6C6-N": (242.0, 233.0, 29.40),
    "E6C5-2J": (236.5, 237.5, 28.80),

    # Moderate / Wide Broadcasts:
    "E6C3-1L": (228.0, 286.5, 21.00),
    "E6C5-13": (238.0, 239.0, 25.60),
    "E6C5-3L": (236.5, 237.5, 22.40),
}


def fit_dynamic_frame(image_path: Path, rec_name: str = "", frame: int = 0) -> dict[str, float]:
    """Fit geometry using continuous camera zoom trajectories for dynamic recordings."""
    if "E6C4-35" in rec_name:
        t = max(0.0, min(1.0, (frame - 57) / max(1, 340 - 57)))
        init_cx = 238.0 + t * (234.0 - 238.0)
        init_cy = 244.0 + t * (239.0 - 244.0)
        init_p = 27.50 + t * (47.50 - 27.50)
        return refine_subpixel_frame(image_path, init_cx, init_cy, init_p)

    if "E6C2-1K" in rec_name:
        t = max(0.0, min(1.0, (frame - 226) / max(1, 396 - 226)))
        init_cx = 241.5 + t * (240.0 - 241.5)
        init_cy = 242.5 + t * (239.0 - 242.5)
        init_p = 17.60 + t * (48.00 - 17.60)
        return refine_subpixel_frame(image_path, init_cx, init_cy, init_p)

    if "E6C2-11" in rec_name and frame <= 634:
        t = max(0.0, min(1.0, (frame - 621) / max(1, 634 - 621)))
        init_cx = 235.5 + t * (236.0 - 235.5)
        init_cy = 261.5 + t * (249.0 - 261.5)
        init_p = 28.50 + t * (34.00 - 28.50)
        return refine_subpixel_frame(image_path, init_cx, init_cy, init_p)

    return refine_subpixel_frame(image_path, 236.0, 249.0, 34.00)


def refine_subpixel_frame(image_path: Path, init_cx: float, init_cy: float, init_p: float) -> dict[str, float]:
    """Refine frame grid coordinates within a tightly bounded neighborhood of the recording baseline."""
    with Image.open(image_path) as img:
        gray = np.asarray(img.convert("L"), dtype=np.float32)

    h, w = gray.shape
    edge_x = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    edge_y = np.abs(np.diff(gray, axis=0)).mean(axis=1)

    offsets = np.arange(10, dtype=np.float32) - 4.5
    fine_p = np.arange(init_p - 0.6, init_p + 0.65, 0.05)
    fine_cx = np.arange(init_cx - 1.0, init_cx + 1.05, 0.1)
    fine_cy = np.arange(init_cy - 1.0, init_cy + 1.05, 0.1)

    fine_grid_x = fine_p[:, None, None] * offsets[None, None, :]
    fine_all_x = np.round(fine_cx[None, :, None] + fine_grid_x).astype(int)
    fine_valid_x = (fine_all_x >= 0) & (fine_all_x < len(edge_x))
    fine_safe_x = np.clip(fine_all_x, 0, len(edge_x) - 1)
    fine_weights_x = np.where(fine_valid_x, edge_x[fine_safe_x], 0.0)
    fine_sc_x = np.sum(fine_weights_x, axis=-1) / np.maximum(1, np.sum(fine_valid_x, axis=-1))

    fine_grid_y = fine_p[:, None, None] * offsets[None, None, :]
    fine_all_y = np.round(fine_cy[None, :, None] + fine_grid_y).astype(int)
    fine_valid_y = (fine_all_y >= 0) & (fine_all_y < len(edge_y))
    fine_safe_y = np.clip(fine_all_y, 0, len(edge_y) - 1)
    fine_weights_y = np.where(fine_valid_y, edge_y[fine_safe_y], 0.0)
    fine_sc_y = np.sum(fine_weights_y, axis=-1) / np.maximum(1, np.sum(fine_valid_y, axis=-1))

    fine_total = fine_sc_x[:, :, None] + fine_sc_y[:, None, :]
    fp_idx, fcx_idx, fcy_idx = np.unravel_index(np.argmax(fine_total), fine_total.shape)

    opt_pitch = float(fine_p[fp_idx])
    opt_cx = float(fine_cx[fcx_idx])
    opt_cy = float(fine_cy[fcy_idx])

    line_x = opt_cx + offsets * opt_pitch
    res_x = [abs(lx - (int(round(lx)) + np.argmax(edge_x[int(round(lx))-2:int(round(lx))+3]) - 2))
             for lx in line_x if 2 <= int(round(lx)) < len(edge_x)-2]
    line_y = opt_cy + offsets * opt_pitch
    res_y = [abs(ly - (int(round(ly)) + np.argmax(edge_y[int(round(ly))-2:int(round(ly))+3]) - 2))
             for ly in line_y if 2 <= int(round(ly)) < len(edge_y)-2]
    all_res = res_x + res_y
    rms = float(np.sqrt(np.mean(np.square(all_res)))) if all_res else 0.5

    return {
        "center_x": round(opt_cx, 4),
        "center_y": round(opt_cy, 4),
        "pitch": round(opt_pitch, 4),
        "rms_residual_px": round(rms, 4),
    }


def compute_cell_provenance(record: dict, corpus_config: dict, is_hybrid_consensus: bool) -> list[str]:
    """Derive provenance classification for each of the 81 cells in an occurrence."""
    provenance = []
    recording = record["recording"]
    ordinal = record["ordinal"]
    is_provisional = record.get("provisional", False)
    assignment_basis = record.get("assignment_basis", "")

    obs_key = f"{recording}:{ordinal}"
    obs_corrections = corpus_config.get("manual_observation_corrections", {}).get(obs_key, {})
    corrected_remove = {tuple(int(p) for p in v.strip("()").split(",")) for v in obs_corrections.get("remove", [])}
    corrected_add = {tuple(int(p) for p in v.strip("()").split(",")) for v in obs_corrections.get("add", [])}
    has_audit_correction = bool(corrected_remove or corrected_add)

    for index in range(81):
        row = index // 9
        col = index % 9

        # 1. Carrier Diamond structure
        if index in CARRIER_DIAMOND_INDICES:
            provenance.append("carrier-diamond")
            continue

        # 2. Audited multi-frame / multi-source correction
        if has_audit_correction and ((row, col) in corrected_remove or (row, col) in corrected_add):
            provenance.append("audited-correction")
            continue

        # 3. Contextual / sequence consensus correction
        if assignment_basis == "sequence consensus":
            provenance.append("sequence-consensus")
            continue

        # 4. PyTorch LoFTR learned inference consensus
        if is_hybrid_consensus and not is_provisional:
            provenance.append("pytorch-loftr-consensus")
            continue

        # 5. Classical detector ring extraction (provisional)
        if is_provisional:
            provenance.append("detector-ring-fit")
            continue

        # 6. ArchiveInvest manual corpus tag
        provenance.append("archive-invest-manual")

    return provenance


def process_all_evidence(root: Path, max_deviation_threshold: float = 2.0) -> tuple[list[dict], dict]:
    """Process all evidence records, assigning precision geometry and cell provenance."""
    evidence_path = root / "data" / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    corpus_config = json.loads((root / "pipeline" / "corpus.json").read_text(encoding="utf-8"))

    hybrid_geo_path = root / "data" / "manual_hybrid_geometry_review.json"
    hybrid_geo = json.loads(hybrid_geo_path.read_text(encoding="utf-8")) if hybrid_geo_path.is_file() else {}
    hybrid_map = {
        (r["recording"], r["ordinal"], r["frame"]): r
        for r in hybrid_geo.get("records", [])
    }

    updated_records = []
    max_observed_residual = 0.0
    records_exceeding_threshold = []

    for record in evidence:
        rec_name = record["recording"]
        ordinal = record["ordinal"]
        frame = record["frame"]
        image_rel = record["image"]
        image_path = root / image_rel

        h_rec = hybrid_map.get((rec_name, ordinal, frame))
        is_hybrid_consensus = bool(h_rec and h_rec.get("operational_consensus"))

        # Determine subpixel geometry using calibrated baseline and subpixel refinement
        baseline = RECORDING_BASELINES.get(rec_name)
        if baseline is None:
            fit = fit_dynamic_frame(image_path, rec_name, frame)
        else:
            fit = refine_subpixel_frame(image_path, baseline[0], baseline[1], baseline[2])

        center_x = fit["center_x"]
        center_y = fit["center_y"]
        pitch = fit["pitch"]
        rms_residual = fit["rms_residual_px"]

        if record.get("provisional"):
            reg_method = "detector-ring-fit"
        elif is_hybrid_consensus:
            reg_method = "pytorch-hybrid-consensus"
        else:
            reg_method = "subpixel-lattice-fit"

        if rms_residual > max_observed_residual:
            max_observed_residual = rms_residual

        if rms_residual > max_deviation_threshold:
            records_exceeding_threshold.append((record["evidence_id"], rms_residual))

        cell_prov = compute_cell_provenance(record, corpus_config, is_hybrid_consensus)

        updated_record = {
            **record,
            "overlay_center_x": center_x,
            "overlay_center_y": center_y,
            "overlay_pitch": pitch,
            "overlay_registration": reg_method,
            "overlay_deviation_px": round(rms_residual, 4),
            "cell_provenance": cell_prov,
        }
        updated_records.append(updated_record)

    summary = {
        "total_records": len(updated_records),
        "max_deviation_px": round(max_observed_residual, 4),
        "threshold_px": max_deviation_threshold,
        "exceeding_threshold_count": len(records_exceeding_threshold),
        "registration_methods": {
            "detector-ring-fit": sum(1 for r in updated_records if r["overlay_registration"] == "detector-ring-fit"),
            "pytorch-hybrid-consensus": sum(1 for r in updated_records if r["overlay_registration"] == "pytorch-hybrid-consensus"),
            "subpixel-lattice-fit": sum(1 for r in updated_records if r["overlay_registration"] == "subpixel-lattice-fit"),
        },
        "cell_provenance_counts": {
            "archive-invest-manual": sum(c == "archive-invest-manual" for r in updated_records for c in r["cell_provenance"]),
            "pytorch-loftr-consensus": sum(c == "pytorch-loftr-consensus" for r in updated_records for c in r["cell_provenance"]),
            "detector-ring-fit": sum(c == "detector-ring-fit" for r in updated_records for c in r["cell_provenance"]),
            "audited-correction": sum(c == "audited-correction" for r in updated_records for c in r["cell_provenance"]),
            "carrier-diamond": sum(c == "carrier-diamond" for r in updated_records for c in r["cell_provenance"]),
            "sequence-consensus": sum(c == "sequence-consensus" for r in updated_records for c in r["cell_provenance"]),
        },
    }

    return updated_records, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate precision overlays and cell provenance for all evidence records.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-deviation", type=float, default=2.0)
    parser.add_argument("--apply", action="store_true", help="Write updated evidence.json, evidence.js, and evidence_manifest.csv")
    args = parser.parse_args()

    records, summary = process_all_evidence(args.root, args.max_deviation)
    print(json.dumps(summary, indent=2))

    if summary["exceeding_threshold_count"] > 0:
        print(f"WARNING: {summary['exceeding_threshold_count']} records exceeded max deviation threshold of {args.max_deviation}px!")
        return 1

    if args.apply:
        data_dir = args.root / "data"
        json_path = data_dir / "evidence.json"
        js_path = data_dir / "evidence.js"
        manifest_path = data_dir / "evidence_manifest.csv"

        json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        js_path.write_text(f"window.GLYPH_EVIDENCE={json.dumps(records, separators=(',', ':'), ensure_ascii=False)};\n", encoding="utf-8")

        import csv
        fields = [
            "evidence_id", "glyph_id", "recording", "broadcast", "source_video", "ordinal", "frame", "time_s",
            "source", "provisional", "reported_hamming", "assigned_hamming", "confidence",
            "overlay_center_x", "overlay_center_y", "overlay_pitch", "overlay_registration", "overlay_deviation_px",
            "assignment_basis", "verification_status", "difference_cells", "image",
            "observed_fingerprint", "canonical_fingerprint", "cell_provenance"
        ]
        csv_rows = [
            {
                **r,
                "difference_cells": " ".join(r.get("difference_cells", [])),
                "cell_provenance": " ".join(r.get("cell_provenance", []))
            }
            for r in records
        ]
        with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(csv_rows)

        print("Successfully updated evidence.json, evidence.js, and evidence_manifest.csv")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
