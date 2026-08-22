from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from analyze_sources import analyze
from build_site import build
from common import find_executable, load_config, resolve_automatic_video, resolve_manual_video


def validate_inputs(config_path: Path, archive: Path, video_dir: Path, ffmpeg_path: str | None) -> dict:
    config = load_config(config_path)
    ffmpeg = find_executable(ffmpeg_path, "ffmpeg")
    required = [
        archive / "PatternCSVs" / "glyph_dictionary.csv",
        archive / "broadcasts.csv",
        archive / "phrases.csv",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    pattern_files = sorted((archive / "PatternCSVs").glob("*_patterns.csv"))
    if not pattern_files:
        missing.append(str(archive / "PatternCSVs" / "*_patterns.csv"))
    manual_sources = {}
    for path in pattern_files:
        broadcast = path.stem.removesuffix("_patterns")
        try:
            manual_sources[broadcast] = resolve_manual_video(archive, broadcast, config).name
        except (FileNotFoundError, KeyError) as error:
            missing.append(str(error))
    automatic_sources = {}
    for source in config.get("automatic_sources", []):
        try:
            automatic_sources[source["broadcast"]] = resolve_automatic_video(video_dir, source["broadcast"], config).name
        except (FileNotFoundError, KeyError) as error:
            missing.append(str(error))
    if missing:
        raise FileNotFoundError("Input check failed:\n- " + "\n- ".join(missing))
    return {
        "ffmpeg": ffmpeg,
        "manual_pattern_files": len(pattern_files),
        "manual_source_videos": len(set(manual_sources.values())),
        "automatic_source_videos": len(set(automatic_sources.values())),
        "manual_overrides": config.get("manual_source_overrides", {}),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the EVE Frontier glyph pipeline end to end.")
    parser.add_argument("--config", type=Path, default=root / "pipeline" / "corpus.json")
    parser.add_argument("--archive-invest", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, default=root)
    parser.add_argument("--workspace", type=Path, default=root / ".pipeline-work")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg; otherwise it must be on PATH.")
    parser.add_argument("--check-inputs", action="store_true", help="Validate paths and exact source resolution, then exit.")
    parser.add_argument("--skip-analysis", action="store_true", help="Reuse workspace/analysis/glyph_sequences.csv and sampled frames.")
    args = parser.parse_args()

    config, archive = args.config.resolve(), args.archive_invest.resolve()
    video_dir, site, workspace = args.video_dir.resolve(), args.site_root.resolve(), args.workspace.resolve()
    inputs = validate_inputs(config, archive, video_dir, args.ffmpeg)
    print(json.dumps({"stage": "inputs", **inputs}, indent=2))
    if args.check_inputs:
        return 0

    analysis_dir = workspace / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_analysis:
        summary = analyze(config, archive, video_dir, analysis_dir, args.ffmpeg)
        print(json.dumps({"stage": "analysis", **summary}, indent=2))
    elif not (analysis_dir / "glyph_sequences.csv").is_file():
        raise FileNotFoundError(f"--skip-analysis requires {analysis_dir / 'glyph_sequences.csv'}")

    stats = build(config, archive, video_dir, analysis_dir, site, args.ffmpeg)
    print(json.dumps({"stage": "site", **stats}, indent=2))
    completed = subprocess.run([sys.executable, str(site / "scripts" / "validate_repository.py")], cwd=site)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
