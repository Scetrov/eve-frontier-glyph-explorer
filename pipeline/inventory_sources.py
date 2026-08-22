from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from common import VIDEO_SUFFIXES, find_executable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FIELDS = (
    "source_set", "filename", "media_type", "bytes", "sha256", "codec",
    "width", "height", "duration_s", "avg_frame_rate", "nb_frames",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path, ffprobe: str) -> dict[str, str | int]:
    command = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        return {"codec": "", "width": "", "height": "", "duration_s": "", "avg_frame_rate": "", "nb_frames": ""}
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    duration = payload.get("format", {}).get("duration", "")
    return {
        "codec": stream.get("codec_name", ""),
        "width": stream.get("width", ""),
        "height": stream.get("height", ""),
        "duration_s": round(float(duration), 6) if duration not in ("", None, "N/A") else "",
        "avg_frame_rate": stream.get("avg_frame_rate", ""),
        "nb_frames": "" if stream.get("nb_frames") in (None, "N/A") else stream.get("nb_frames"),
    }


def collect(directory: Path, source_set: str, ffprobe: str, include_images: bool) -> list[dict]:
    suffixes = VIDEO_SUFFIXES | (IMAGE_SUFFIXES if include_images else set())
    rows = []
    for path in sorted((item for item in directory.iterdir() if item.is_file() and item.suffix.lower() in suffixes), key=lambda item: item.name.lower()):
        media_type = "video" if path.suffix.lower() in VIDEO_SUFFIXES else "image"
        rows.append({
            "source_set": source_set,
            "filename": path.name,
            "media_type": media_type,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            **probe(path, ffprobe),
        })
    return rows


def write_manifest(rows: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_version": 1,
        "hash_algorithm": "SHA-256",
        "scope": "Locally available source media; paths are intentionally omitted.",
        "entries": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def verify(directory: Path, source_set: str, entries: list[dict]) -> list[str]:
    errors = []
    for row in entries:
        if row["source_set"] != source_set:
            continue
        path = directory / row["filename"]
        if not path.is_file():
            errors.append(f"missing: {source_set}/{row['filename']}")
        elif path.stat().st_size != int(row["bytes"]):
            errors.append(f"size mismatch: {source_set}/{row['filename']}")
        elif sha256(path) != row["sha256"]:
            errors.append(f"SHA-256 mismatch: {source_set}/{row['filename']}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Create or verify the source-media integrity manifest.")
    parser.add_argument("--downloaded-dir", type=Path, required=True)
    parser.add_argument("--archive-video-dir", type=Path, required=True)
    parser.add_argument("--ffprobe", help="Path to ffprobe; otherwise it must be on PATH.")
    parser.add_argument("--json", type=Path, default=root / "data" / "source_integrity.json")
    parser.add_argument("--csv", type=Path, default=root / "data" / "source_integrity.csv")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    downloaded = args.downloaded_dir.resolve()
    archive = args.archive_video_dir.resolve()
    if args.verify:
        payload = json.loads(args.json.read_text(encoding="utf-8"))
        errors = verify(downloaded, "downloaded", payload["entries"])
        errors += verify(archive, "archiveinvest", payload["entries"])
        print(json.dumps({"entries": len(payload["entries"]), "errors": errors}, indent=2))
        return 1 if errors else 0

    ffprobe = find_executable(args.ffprobe, "ffprobe")
    rows = collect(downloaded, "downloaded", ffprobe, include_images=True)
    rows += collect(archive, "archiveinvest", ffprobe, include_images=False)
    write_manifest(rows, args.json, args.csv)
    print(json.dumps({"entries": len(rows), "videos": sum(row["media_type"] == "video" for row in rows), "images": sum(row["media_type"] == "image" for row in rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
