from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path


VIDEO_SUFFIXES = {".mov", ".mp4", ".webm", ".mkv"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("version") != 1:
        raise ValueError(f"Unsupported corpus config version in {path}")
    broadcasts = [item["broadcast"] for item in config.get("automatic_sources", [])]
    if len(broadcasts) != len(set(broadcasts)):
        raise ValueError("automatic_sources contains duplicate broadcast labels")
    return config


def find_executable(explicit: str | None, name: str) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{name} not found: {path}")
        return str(path)
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"{name} is required and was not found on PATH")
    return found


def run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        rendered = subprocess.list2cmdline(command)
        raise RuntimeError(f"Command failed ({completed.returncode}): {rendered}\n{completed.stderr.strip()}")


def parse_cells(text: str) -> list[int]:
    return sorted(int(row) * 9 + int(column) for row, column in re.findall(r"\((\d+)\s+(\d+)\)", text or ""))


def fingerprint_from_cells(cells: list[int]) -> str:
    active = set(cells)
    return "".join("1" if index in active else "0" for index in range(81))


def hamming(left: str, right: str) -> int:
    if len(left) != 81 or len(right) != 81:
        raise ValueError("Hamming inputs must be 81-bit fingerprints")
    return sum(a != b for a, b in zip(left, right))


def cycle_label(name: str) -> str:
    match = re.search(r"E(\d+)C(\d+)", name)
    if match:
        return f"E{match.group(1)}C{match.group(2)}"
    return "Era 5 legacy" if name.lower().startswith("youtube") else "Unknown"


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def automatic_source_map(config: dict) -> dict[str, dict]:
    return {item["broadcast"]: item for item in config.get("automatic_sources", [])}


def sample_frames(source: dict) -> list[int]:
    if source.get("sample_frames"):
        frames = [int(value) for value in source["sample_frames"]]
    else:
        required = ("first_change", "last_change", "last_safe")
        missing = [key for key in required if key not in source]
        if missing:
            raise ValueError(f"{source['broadcast']} is missing sampling keys: {missing}")
        cadence = int(source.get("cadence", 6))
        offset = int(source.get("sample_offset", cadence - 1))
        transitions = range(int(source["first_change"]), int(source["last_change"]) + 1, cadence)
        frames = [min(frame + offset, int(source["last_safe"])) for frame in transitions]
    if not frames or frames != sorted(set(frames)):
        raise ValueError(f"{source['broadcast']} sample frames must be non-empty, unique, and ascending")
    return frames


def resolve_manual_video(archive_invest: Path, broadcast: str, config: dict) -> Path:
    video_dir = archive_invest / "Videos"
    override = config.get("manual_source_overrides", {}).get(broadcast)
    if override:
        path = video_dir / override
        if not path.is_file():
            raise FileNotFoundError(f"Mapped manual source is missing: {path}")
        return path
    exact = video_dir / f"{broadcast}.mp4"
    if exact.is_file():
        return exact
    matches = sorted(path for path in video_dir.glob(f"{broadcast}.*") if path.suffix.lower() in VIDEO_SUFFIXES)
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one exact source for {broadcast}; found: {[path.name for path in matches]}")
    return matches[0]


def resolve_automatic_video(video_dir: Path, broadcast: str, config: dict) -> Path:
    source = automatic_source_map(config).get(broadcast)
    if not source:
        raise KeyError(f"No automatic source config for {broadcast}")
    path = video_dir / source["file"]
    if not path.is_file():
        raise FileNotFoundError(f"Automatic source is missing: {path}")
    return path
