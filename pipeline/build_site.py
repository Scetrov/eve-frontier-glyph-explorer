from __future__ import annotations

import csv
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import (
    cycle_label,
    fingerprint_from_cells,
    find_executable,
    hamming,
    load_config,
    parse_cells,
    read_csv,
    resolve_automatic_video,
    resolve_manual_video,
    run,
    safe_slug,
)


OCCURRENCE_FIELDS = [
    "glyph_id", "recording", "broadcast", "cycle", "track", "ordinal", "frame", "time_s",
    "source", "provisional", "hamming_distance", "confidence", "overlay_center_x", "overlay_center_y", "overlay_pitch", "overlay_registration", "assignment_basis", "verification_status", "observed_fingerprint",
]


def corrected_cells(cells: list[int], correction: dict | None) -> list[int]:
    result = set(cells)
    for value in (correction or {}).get("remove", []):
        row, column = (int(part) for part in value.strip("()").split(","))
        result.discard(row * 9 + column)
    for value in (correction or {}).get("add", []):
        row, column = (int(part) for part in value.strip("()").split(","))
        result.add(row * 9 + column)
    return sorted(result)


def transform_distance(fingerprint: str, operation: str) -> int:
    grid = [list(fingerprint[row * 9 : row * 9 + 9]) for row in range(9)]
    transforms = {
        "horizontal": [row[::-1] for row in grid],
        "vertical": grid[::-1],
        "rotate180": [row[::-1] for row in grid[::-1]],
        "transpose": [[grid[column][row] for column in range(9)] for row in range(9)],
    }
    return sum(grid[row][column] != transforms[operation][row][column] for row in range(9) for column in range(9))


def connected_components(glyph_ids: list[int], edges: list[tuple[int, int]]) -> dict[int, tuple[int, int]]:
    graph = {glyph_id: set() for glyph_id in glyph_ids}
    for left, right in edges:
        graph[left].add(right)
        graph[right].add(left)
    result, seen, family = {}, set(), 0
    for glyph_id in glyph_ids:
        if glyph_id in seen:
            continue
        family += 1
        stack, members = [glyph_id], []
        seen.add(glyph_id)
        while stack:
            node = stack.pop()
            members.append(node)
            for neighbour in graph[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        for node in members:
            result[node] = (family, len(members))
    return result


def repeated_blocks(sequences: dict[str, list[int]]) -> list[dict]:
    blocks: dict[tuple[int, ...], set[str]] = defaultdict(set)
    for recording, sequence in sequences.items():
        for length in range(5, len(sequence) + 1):
            for start in range(len(sequence) - length + 1):
                blocks[tuple(sequence[start : start + length])].add(recording)
    longest: dict[tuple[str, ...], dict] = {}
    for block, recordings in blocks.items():
        if len(recordings) < 2:
            continue
        row = {"length": len(block), "glyph_ids": list(block), "broadcasts": sorted(recordings), "n_broadcasts": len(recordings)}
        key = tuple(row["broadcasts"])
        if key not in longest or row["length"] > longest[key]["length"]:
            longest[key] = row
    candidates = list(longest.values())
    selected = sorted(candidates, key=lambda item: (-item["length"], -item["n_broadcasts"], item["glyph_ids"]))[:4]
    for row in sorted(candidates, key=lambda item: (-item["n_broadcasts"], -item["length"], item["glyph_ids"])):
        if row not in selected:
            selected.append(row)
        if len(selected) == 12:
            break
    return selected


def load_inputs(config: dict, archive: Path, automatic_csv: Path) -> tuple[dict[int, dict], list[dict], dict[int, list[dict]], dict[str, str]]:
    dictionary = {}
    by_fingerprint = {}
    for row in read_csv(archive / "PatternCSVs" / "glyph_dictionary.csv"):
        glyph_id, fingerprint = int(row["glyph_id"]), row["fingerprint"]
        cells = [index for index, bit in enumerate(fingerprint) if bit == "1"]
        cells = corrected_cells(cells, config.get("canonical_cell_corrections", {}).get(str(glyph_id)))
        fingerprint = fingerprint_from_cells(cells)
        dictionary[glyph_id] = {
            "id": glyph_id, "fingerprint": fingerprint, "cell_indices": cells,
            "cells": " ".join(f"({index // 9},{index % 9})" for index in cells), "n_cells": len(cells),
            "first_video": row["first_video"], "first_frame": int(float(row["first_frame"])),
            "first_time_s": float(row["first_time_s"]),
        }
        by_fingerprint[fingerprint] = glyph_id

    phrases: dict[int, list[dict]] = defaultdict(list)
    for row in read_csv(archive / "phrases.csv"):
        for value in row["glyph_ids"].replace(",", " ").split():
            if value.isdigit():
                phrases[int(value)].append({"phrase": row["phrase"], "role": row["role"]})

    tracks = {row["broadcast"]: row["track"] for row in read_csv(archive / "broadcasts.csv")}
    tracks.update(config.get("track_overrides", {}))
    occurrences, manual_broadcasts = [], set()
    for path in sorted((archive / "PatternCSVs").glob("*_patterns.csv")):
        broadcast = path.stem.removesuffix("_patterns")
        manual_broadcasts.add(broadcast)
        for ordinal, row in enumerate(read_csv(path), 1):
            observation_key = f"{broadcast}:{ordinal}"
            cells = corrected_cells(parse_cells(row.get("cells", "")), config.get("manual_observation_corrections", {}).get(observation_key))
            fingerprint = fingerprint_from_cells(cells)
            glyph_id = by_fingerprint.get(fingerprint)
            distance, basis = 0, "matches corpus tag"
            if glyph_id is None:
                glyph_id, distance = min(
                    ((candidate, hamming(fingerprint, glyph["fingerprint"])) for candidate, glyph in dictionary.items()),
                    key=lambda item: item[1],
                )
                basis = "nearest corpus tag"
            verification = "multi-source audited" if observation_key == "E6C4-17:7" else "multi-frame audited" if observation_key == "E6C4-35:38" else "corpus tag; not independently verified"
            occurrences.append({
                "glyph_id": glyph_id, "recording": broadcast, "broadcast": broadcast,
                "cycle": cycle_label(broadcast), "track": tracks.get(broadcast, "Unknown"), "ordinal": ordinal,
                "frame": int(float(row.get("frame") or 0)), "time_s": round(float(row.get("time_s") or 0), 4),
                "source": "ArchiveInvest manual", "provisional": False, "hamming_distance": distance,
                "confidence": "", "assignment_basis": basis, "verification_status": verification, "observed_fingerprint": fingerprint,
                "overlay_center_x": None, "overlay_center_y": None, "overlay_pitch": None, "overlay_registration": None,
            })

    corrections = config.get("context_corrections", {})
    for row in read_csv(automatic_csv):
        broadcast, ordinal = row["video"], int(row["glyph_index"])
        nearest = int(row["nearest_glyph_id"])
        glyph_id = int(corrections.get(f"{broadcast}:{ordinal}", nearest))
        occurrences.append({
            "glyph_id": glyph_id,
            "recording": f"{broadcast} [local capture]" if broadcast in manual_broadcasts else broadcast,
            "broadcast": broadcast, "cycle": cycle_label(broadcast), "track": tracks.get(broadcast, "Unknown"),
            "ordinal": ordinal, "frame": int(row["frame"]), "time_s": round(float(row["time_s"]), 4),
            "source": "FFmpeg automatic extraction", "provisional": True,
            "hamming_distance": int(row["hamming_distance"]),
            "confidence": round(float(row["classification_confidence"]), 4),
            "assignment_basis": "sequence consensus" if glyph_id != nearest else "automatic nearest glyph",
            "verification_status": "provisional automatic read",
            "observed_fingerprint": row["fingerprint"],
            "overlay_center_x": round(float(row["center_x"]) * 4 / 9, 4),
            "overlay_center_y": round(float(row["center_y"]) * 4 / 9, 4),
            "overlay_pitch": round(float(row["pitch_px"]) * 4 / 9, 4),
            "overlay_registration": "detector-ring-fit",
        })
    occurrence_counts = Counter(row["glyph_id"] for row in occurrences)
    for row in occurrences:
        if row["provisional"] or row["glyph_id"] in (130, 140):
            continue
        row["verification_status"] = (
            "single-source corpus entry; unverified"
            if occurrence_counts[row["glyph_id"]] == 1
            else "matches repeated corpus observations"
        )
    occurrences.sort(key=lambda item: (item["recording"], item["ordinal"]))
    return dictionary, occurrences, phrases, tracks


def derive_catalogue(dictionary: dict[int, dict], occurrences: list[dict], phrases: dict[int, list[dict]], tracks: dict[str, str]) -> dict:
    by_glyph, by_recording = defaultdict(list), defaultdict(list)
    for occurrence in occurrences:
        by_glyph[occurrence["glyph_id"]].append(occurrence)
        by_recording[occurrence["recording"]].append(occurrence)
    sequences = {name: [row["glyph_id"] for row in sorted(rows, key=lambda item: item["ordinal"])] for name, rows in by_recording.items()}
    successors, predecessors = defaultdict(Counter), defaultdict(Counter)
    adjacent = []
    for sequence in sequences.values():
        for left, right in zip(sequence, sequence[1:]):
            successors[left][right] += 1
            predecessors[right][left] += 1
            adjacent.append(hamming(dictionary[left]["fingerprint"], dictionary[right]["fingerprint"]))

    glyph_ids, pair_distances, edges = sorted(dictionary), [], []
    near = defaultdict(list)
    distance_one = distance_two = 0
    for position, left in enumerate(glyph_ids):
        for right in glyph_ids[position + 1 :]:
            distance = hamming(dictionary[left]["fingerprint"], dictionary[right]["fingerprint"])
            pair_distances.append(distance)
            if distance <= 2:
                near[left].append({"id": right, "distance": distance})
                near[right].append({"id": left, "distance": distance})
                edges.append((left, right))
                distance_one += distance == 1
                distance_two += distance == 2
    families = connected_components(glyph_ids, edges)
    cell_usage = [0] * 81
    for glyph in dictionary.values():
        for index in glyph["cell_indices"]:
            cell_usage[index] += 1

    catalogue = []
    for glyph_id in glyph_ids:
        base, rows = dictionary[glyph_id], by_glyph[glyph_id]
        recordings = sorted({row["recording"] for row in rows})
        broadcasts = sorted({row["broadcast"] for row in rows})
        phrase_rows = phrases.get(glyph_id, [])
        all_distances = [hamming(base["fingerprint"], dictionary[other]["fingerprint"]) for other in glyph_ids if other != glyph_id]
        family_id, family_size = families[glyph_id]
        if glyph_id == 130:
            verification_status = "multi-source, multi-frame audited"
        elif glyph_id == 140:
            verification_status = "multi-frame audited"
        elif len(rows) == 1:
            verification_status = "single-source corpus entry; unverified"
        else:
            verification_status = "supported by repeated corpus occurrences"
        catalogue.append({
            **base, "occurrences": len(rows), "manual_occurrences": sum(not row["provisional"] for row in rows),
            "provisional_occurrences": sum(row["provisional"] for row in rows), "broadcast_count": len(broadcasts),
            "recording_count": len(recordings), "recordings": recordings, "broadcasts": broadcasts,
            "cycles": sorted({row["cycle"] for row in rows}), "phrases": [row["phrase"] for row in phrase_rows],
            "phrase_roles": [row["role"] for row in phrase_rows],
            "near_twins": sorted(near[glyph_id], key=lambda item: (item["distance"], item["id"])),
            "nearest_neighbour_distance": min(all_distances), "family_id": family_id, "family_size": family_size,
            "successors": [{"id": item, "count": count} for item, count in successors[glyph_id].most_common(6)],
            "predecessors": [{"id": item, "count": count} for item, count in predecessors[glyph_id].most_common(6)],
            "symmetry": {operation: transform_distance(base["fingerprint"], operation) for operation in ("horizontal", "vertical", "rotate180", "transpose")},
            "verification_status": verification_status,
            "occurrence_samples": [{key: row[key] for key in ("recording", "broadcast", "ordinal", "time_s", "source", "provisional", "hamming_distance")} for row in rows[:18]],
        })

    frequencies = Counter(row["glyph_id"] for row in occurrences)
    total = len(occurrences)
    probabilities = [count / total for count in frequencies.values()]
    entropy = -sum(probability * math.log2(probability) for probability in probabilities)
    coincidence = sum(count * (count - 1) for count in frequencies.values()) / (total * (total - 1))
    stats = {
        "canonical_glyphs": len(catalogue), "recordings": len(sequences),
        "broadcasts": len({row["broadcast"] for row in occurrences}), "occurrences": total,
        "manual_occurrences": sum(not row["provisional"] for row in occurrences),
        "provisional_occurrences": sum(row["provisional"] for row in occurrences), "observed_glyphs": len(frequencies),
        "singleton_glyphs": sum(count == 1 for count in frequencies.values()),
        "used_grid_cells": sum(value > 0 for value in cell_usage), "unused_grid_cells": sum(value == 0 for value in cell_usage),
        "active_cells_mean": round(sum(glyph["n_cells"] for glyph in catalogue) / len(catalogue), 3),
        "active_cells_min": min(glyph["n_cells"] for glyph in catalogue), "active_cells_max": max(glyph["n_cells"] for glyph in catalogue),
        "token_entropy_bits": round(entropy, 4), "max_entropy_bits": round(math.log2(len(catalogue)), 4),
        "normalised_entropy": round(entropy / math.log2(len(catalogue)), 4), "index_of_coincidence": round(coincidence, 6),
        "distance_one_pairs": distance_one, "distance_two_pairs": distance_two,
        "all_pair_mean_hamming": round(sum(pair_distances) / len(pair_distances), 3),
        "adjacent_mean_hamming": round(sum(adjacent) / len(adjacent), 3),
        "adjacent_median_hamming": sorted(adjacent)[len(adjacent) // 2],
        "near_twin_families": len({family for family, size in families.values() if size > 1}),
        "largest_near_twin_family": max(size for _, size in families.values()),
        "unmatched_manual_rows": sum(row["assignment_basis"] == "nearest corpus tag" for row in occurrences),
    }
    sequence_rows = []
    for recording in sorted(sequences):
        rows = by_recording[recording]
        broadcast = rows[0]["broadcast"]
        distances = [row["hamming_distance"] for row in rows if row["provisional"]]
        sequence_rows.append({
            "recording": recording, "broadcast": broadcast, "cycle": cycle_label(broadcast),
            "track": tracks.get(broadcast, "Unknown"), "n_glyphs": len(rows),
            "source": "provisional FFmpeg read" if distances else "manual ArchiveInvest tags",
            "mean_hamming": round(sum(distances) / len(distances), 3) if distances else 0,
            "uncertain_gt2": sum(distance > 2 for distance in distances),
            "glyph_ids": " ".join(str(value) for value in sequences[recording]),
        })
    return {
        "stats": stats, "glyphs": catalogue, "sequences": sequence_rows,
        "repeated_blocks": repeated_blocks(sequences), "cell_usage": cell_usage,
        "notes": {
            "provisional": "Configured local captures were classified automatically; contextual corrections are declared in pipeline/corpus.json. Duplicate logical broadcasts remain separate recordings.",
            "carrier": "The atlas shows payload cells only. A symmetric 28-cell mask is supported after multi-frame review corrected two singleton carrier-edge marks.",
        },
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_atlas(glyphs: list[dict], path: Path) -> None:
    columns, tile_width, tile_height, margin_x, margin_y = 10, 178, 188, 28, 88
    image = Image.new("RGB", (margin_x * 2 + columns * tile_width, margin_y + math.ceil(len(glyphs) / columns) * tile_height + 70), "#0b0b0b")
    draw, font, small = ImageDraw.Draw(image), ImageFont.load_default(size=18), ImageFont.load_default(size=13)
    draw.text((margin_x, 22), f"EVE Frontier glyph atlas — {len(glyphs)} canonical payload patterns", fill="#fafae5", font=font)
    draw.text((margin_x, 50), "Martian red = active payload cell; carrier diamond and video effects omitted", fill="#fafae5", font=small)
    for index, glyph in enumerate(glyphs):
        row, column = divmod(index, columns)
        x0, y0 = margin_x + column * tile_width, margin_y + row * tile_height
        draw.rounded_rectangle((x0 + 4, y0 + 4, x0 + tile_width - 8, y0 + tile_height - 10), radius=8, fill="#0b0b0b", outline="#fafae5")
        draw.text((x0 + 15, y0 + 13), f"#{glyph['id']}", fill="#fafae5", font=font)
        draw.text((x0 + 88, y0 + 17), f"n={glyph['occurrences']}", fill="#fafae5", font=small)
        active = set(glyph["cell_indices"])
        for grid_row in range(9):
            for grid_column in range(9):
                x, y = x0 + 26 + grid_column * 13, y0 + 48 + grid_row * 13
                draw.rounded_rectangle((x, y, x + 9, y + 9), radius=2, fill="#ff4700" if grid_row * 9 + grid_column in active else "#0b0b0b", outline="#fafae5")
        clusters = ",".join(glyph["phrases"]) if glyph["phrases"] else "-"
        draw.text((x0 + 15, y0 + 169), f"{glyph['n_cells']} cells · cluster {clusters}", fill="#fafae5", font=small)
    image.save(path, optimize=True)


def write_catalogue(site: Path, data: dict, occurrences: list[dict]) -> None:
    data_dir = site / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    (data_dir / "catalogue.json").write_text(json_text, encoding="utf-8")
    (data_dir / "catalogue.js").write_text(f"window.GLYPH_DATA={json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n", encoding="utf-8")
    write_csv(data_dir / "glyph_occurrences.csv", occurrences, OCCURRENCE_FIELDS)
    write_csv(data_dir / "sequences.csv", data["sequences"], list(data["sequences"][0]))
    fields = ["glyph_id", "fingerprint", "n_cells", "cells", "occurrences", "manual_occurrences", "provisional_occurrences", "recording_count", "recordings", "broadcast_count", "broadcasts", "cycles", "phrase_clusters", "phrase_roles", "near_twins_d1", "near_twins_d2", "nearest_neighbour_distance", "family_id", "family_size", "top_predecessors", "top_successors", "first_video", "first_frame", "first_time_s"]
    rows = []
    for glyph in data["glyphs"]:
        rows.append({
            "glyph_id": glyph["id"], "fingerprint": glyph["fingerprint"], "n_cells": glyph["n_cells"], "cells": glyph["cells"],
            "occurrences": glyph["occurrences"], "manual_occurrences": glyph["manual_occurrences"], "provisional_occurrences": glyph["provisional_occurrences"],
            "recording_count": glyph["recording_count"], "recordings": "; ".join(glyph["recordings"]), "broadcast_count": glyph["broadcast_count"],
            "broadcasts": "; ".join(glyph["broadcasts"]), "cycles": "; ".join(glyph["cycles"]), "phrase_clusters": "; ".join(glyph["phrases"]),
            "phrase_roles": "; ".join(glyph["phrase_roles"]), "near_twins_d1": "; ".join(str(item["id"]) for item in glyph["near_twins"] if item["distance"] == 1),
            "near_twins_d2": "; ".join(str(item["id"]) for item in glyph["near_twins"] if item["distance"] == 2),
            "nearest_neighbour_distance": glyph["nearest_neighbour_distance"], "family_id": glyph["family_id"], "family_size": glyph["family_size"],
            "top_predecessors": "; ".join(f"{item['id']}×{item['count']}" for item in glyph["predecessors"]),
            "top_successors": "; ".join(f"{item['id']}×{item['count']}" for item in glyph["successors"]),
            "first_video": glyph["first_video"], "first_frame": glyph["first_frame"], "first_time_s": glyph["first_time_s"],
        })
    write_csv(data_dir / "glyph_catalogue.csv", rows, fields)
    render_atlas(data["glyphs"], site / "assets" / "glyph-atlas.png")


def image_overlay_geometry(image_path: Path) -> dict[str, float | str]:
    """Fit the 9x9 cell lattice to a final evidence crop without consulting its tag.

    Each cell retains a visible horizontal and vertical border even when its central
    aperture changes. Maximising edge energy at those predicted borders therefore
    gives a reproducible visual registration, including for manual corpus tags that
    have no detector geometry in their source CSV.
    """
    with Image.open(image_path) as image:
        gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.shape != (480, 480):
        raise ValueError(f"Expected a 480x480 evidence crop, got {gray.shape} at {image_path}")

    # The source crops use a common, near-centred carrier treatment. Constraining
    # the fit to the observed 28–34 px payload-cell band prevents a large diamond
    # edge or UI texture from being mistaken for a cell border in sparse frames.
    edge_x = np.abs(np.diff(gray, axis=1))
    edge_y = np.abs(np.diff(gray, axis=0))
    projection_x = edge_x[105:375].mean(axis=0)
    projection_y = edge_y[:, 105:375].mean(axis=1)
    offsets = np.array([value for cell in range(9) for value in (cell - 4.40, cell - 3.60)], dtype=np.float32)
    pitches = np.arange(28.0, 34.01, 0.25)
    centres = np.arange(215.0, 265.01, 0.5)

    def fit_axis(projection: np.ndarray, allowed_pitches: np.ndarray) -> tuple[float, float]:
        candidates: list[tuple[float, float, float]] = []
        for pitch in allowed_pitches:
            positions = centres[:, None] + offsets[None, :] * pitch
            indices = np.clip(np.rint(positions).astype(np.int32), 0, len(projection) - 1)
            scores = projection[indices].mean(axis=1)
            best = int(np.argmax(scores))
            candidates.append((float(scores[best]), float(pitch), float(centres[best])))
        _, pitch, centre = max(candidates)
        return pitch, centre

    pitch_x, _ = fit_axis(projection_x, pitches)
    pitch_y, _ = fit_axis(projection_y, pitches)
    pitch = round((pitch_x + pitch_y) / 2, 4)
    _, center_x = fit_axis(projection_x, np.array([pitch]))
    _, center_y = fit_axis(projection_y, np.array([pitch]))
    return {
        "overlay_center_x": round(center_x, 4),
        "overlay_center_y": round(center_y, 4),
        "overlay_pitch": pitch,
        "overlay_registration": "image-edge-fit",
    }


def evidence_record(row: dict, video: Path, destination: Path, site: Path, dictionary: dict[int, dict], overlay: dict | None = None) -> dict:
    canonical, observed = dictionary[row["glyph_id"]]["fingerprint"], row["observed_fingerprint"]
    differences = [index for index, (left, right) in enumerate(zip(canonical, observed)) if left != right]
    return {
        "evidence_id": f"{safe_slug(row['recording'])}-g{row['ordinal']:03d}-f{row['frame']:06d}",
        "glyph_id": row["glyph_id"], "recording": row["recording"], "broadcast": row["broadcast"],
        "source_video": video.name, "ordinal": row["ordinal"], "frame": row["frame"], "time_s": row["time_s"],
        "source": row["source"], "provisional": row["provisional"], "reported_hamming": row["hamming_distance"],
        "assigned_hamming": len(differences), "confidence": row["confidence"] if row["confidence"] != "" else None,
        "overlay_center_x": (overlay or row).get("overlay_center_x"), "overlay_center_y": (overlay or row).get("overlay_center_y"), "overlay_pitch": (overlay or row).get("overlay_pitch"),
        "overlay_registration": (overlay or row).get("overlay_registration"),
        "assignment_basis": row["assignment_basis"], "verification_status": row["verification_status"], "difference_cells": [f"({index // 9},{index % 9})" for index in differences],
        "image": destination.relative_to(site).as_posix(), "observed_fingerprint": observed, "canonical_fingerprint": canonical,
    }


def extract_manual(recording: str, rows: list[dict], archive: Path, config: dict, ffmpeg: str, evidence_root: Path, site: Path, dictionary: dict[int, dict]) -> list[dict]:
    video = resolve_manual_video(archive, rows[0]["broadcast"], config)
    output = evidence_root / safe_slug(recording)
    output.mkdir(parents=True, exist_ok=True)
    frames = list(dict.fromkeys(row["frame"] for row in rows))
    with tempfile.TemporaryDirectory(prefix="glyph-evidence-") as temp_name:
        selected = "+".join(f"eq(n\\,{frame})" for frame in frames)
        video_filter = f"select={selected},crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=480:480:flags=lanczos"
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", video_filter, "-fps_mode", "vfr", "-q:v", "3", str(Path(temp_name) / "frame_%04d.jpg")])
        extracted = sorted(Path(temp_name).glob("frame_*.jpg"))
        if len(extracted) != len(frames):
            raise RuntimeError(f"Expected {len(frames)} frames from {video.name}, extracted {len(extracted)}")
        source_by_frame = dict(zip(frames, extracted))
        records = []
        for row in rows:
            destination = output / f"g{row['ordinal']:03d}_f{row['frame']:06d}.jpg"
            shutil.copy2(source_by_frame[row["frame"]], destination)
            records.append(evidence_record(row, video, destination, site, dictionary, image_overlay_geometry(destination)))
        return records


def copy_automatic(recording: str, rows: list[dict], video_dir: Path, analysis: Path, config: dict, evidence_root: Path, site: Path, dictionary: dict[int, dict]) -> list[dict]:
    video = resolve_automatic_video(video_dir, rows[0]["broadcast"], config)
    output = evidence_root / safe_slug(recording)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for row in rows:
        source = analysis / "frames" / row["broadcast"] / f"glyph_{row['ordinal']:02d}_f{row['frame']:04d}.jpg"
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = output / f"g{row['ordinal']:03d}_f{row['frame']:06d}.jpg"
        with Image.open(source) as image:
            image.convert("RGB").resize((480, 480), Image.Resampling.LANCZOS).save(destination, "JPEG", quality=82, optimize=True)
        records.append(evidence_record(row, video, destination, site, dictionary))
    return records


def build_evidence(site: Path, archive: Path, video_dir: Path, analysis: Path, config: dict, ffmpeg: str, dictionary: dict[int, dict], occurrences: list[dict]) -> None:
    grouped = defaultdict(list)
    for row in occurrences:
        grouped[row["recording"]].append(row)
    staging = site / ".pipeline-work" / "evidence-next"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    records = []
    manual = {name: rows for name, rows in grouped.items() if not rows[0]["provisional"]}
    automatic = {name: rows for name, rows in grouped.items() if rows[0]["provisional"]}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(extract_manual, name, rows, archive, config, ffmpeg, staging, site, dictionary): name for name, rows in manual.items()}
        for future in as_completed(futures):
            batch = future.result()
            records.extend(batch)
            print(f"Extracted {len(batch):>3} manual frames: {futures[future]}")
    for name, rows in automatic.items():
        batch = copy_automatic(name, rows, video_dir, analysis, config, staging, site, dictionary)
        records.extend(batch)
        print(f"Copied    {len(batch):>3} analysed frames: {name}")
    records.sort(key=lambda item: (item["recording"], item["ordinal"]))
    if len(records) != len(occurrences):
        raise RuntimeError(f"Expected {len(occurrences)} evidence records, got {len(records)}")
    current = site / "evidence"
    backup = site / ".pipeline-work" / "evidence-previous"
    if backup.exists():
        shutil.rmtree(backup)
    if current.exists():
        current.replace(backup)
    preserved_audits = backup / "audits"
    if preserved_audits.is_dir():
        shutil.copytree(preserved_audits, staging / "audits")
    staging.replace(current)
    shutil.rmtree(backup, ignore_errors=True)
    for record in records:
        record["image"] = record["image"].replace(".pipeline-work/evidence-next/", "evidence/")
    data_dir = site / "data"
    (data_dir / "evidence.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (data_dir / "evidence.js").write_text(f"window.GLYPH_EVIDENCE={json.dumps(records, separators=(',', ':'), ensure_ascii=False)};\n", encoding="utf-8")
    fields = ["evidence_id", "glyph_id", "recording", "broadcast", "source_video", "ordinal", "frame", "time_s", "source", "provisional", "reported_hamming", "assigned_hamming", "confidence", "overlay_center_x", "overlay_center_y", "overlay_pitch", "overlay_registration", "assignment_basis", "verification_status", "difference_cells", "image", "observed_fingerprint", "canonical_fingerprint"]
    csv_rows = [{**record, "difference_cells": " ".join(record["difference_cells"])} for record in records]
    write_csv(data_dir / "evidence_manifest.csv", csv_rows, fields)


def build(config_path: Path, archive: Path, video_dir: Path, analysis: Path, site: Path, ffmpeg_path: str | None = None) -> dict:
    config, ffmpeg = load_config(config_path), find_executable(ffmpeg_path, "ffmpeg")
    automatic_csv = analysis / "glyph_sequences.csv"
    if not automatic_csv.is_file():
        raise FileNotFoundError(f"Run the analysis stage first: {automatic_csv}")
    dictionary, occurrences, phrases, tracks = load_inputs(config, archive, automatic_csv)
    data = derive_catalogue(dictionary, occurrences, phrases, tracks)
    write_catalogue(site, data, occurrences)
    build_evidence(site, archive, video_dir, analysis, config, ffmpeg, dictionary, occurrences)
    return data["stats"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build the static catalogue and frame evidence.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    print(json.dumps(build(args.config.resolve(), args.archive_invest.resolve(), args.video_dir.resolve(), args.analysis_dir.resolve(), args.site_root.resolve(), args.ffmpeg), indent=2))
