from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SKILLS = ROOT / ".agents" / "skills"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_js_payload(path: Path, variable: str):
    text = path.read_text(encoding="utf-8").strip()
    prefix = f"window.{variable}="
    if not text.startswith(prefix) or not text.endswith(";"):
        raise ValueError(f"{path.relative_to(ROOT)} must be {prefix}<JSON>;")
    return json.loads(text[len(prefix) : -1])


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_skills(errors: list[str]) -> int:
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    if not skill_files:
        fail(errors, "No skills found under .agents/skills")
        return 0

    name_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
        if not match:
            fail(errors, f"{path.relative_to(ROOT)} has no YAML frontmatter")
            continue
        frontmatter = match.group(1)
        name_match = re.search(r"^name:\s*(.+?)\s*$", frontmatter, flags=re.MULTILINE)
        description_match = re.search(r"^description:\s*(.+?)\s*$", frontmatter, flags=re.MULTILINE)
        if not name_match or not description_match:
            fail(errors, f"{path.relative_to(ROOT)} requires name and description")
            continue
        name = name_match.group(1).strip('"\'')
        description = description_match.group(1).strip('"\'')
        if name != path.parent.name:
            fail(errors, f"Skill name {name!r} does not match directory {path.parent.name!r}")
        if not name_pattern.fullmatch(name) or len(name) > 64:
            fail(errors, f"Invalid skill name: {name!r}")
        if not 1 <= len(description) <= 1024:
            fail(errors, f"Invalid description length for {name}")
    return len(skill_files)


def main() -> int:
    errors: list[str] = []

    catalogue = read_json(DATA / "catalogue.json")
    catalogue_js = read_js_payload(DATA / "catalogue.js", "GLYPH_DATA")
    if catalogue_js != catalogue:
        fail(errors, "catalogue.js payload differs from catalogue.json")

    cycles = read_json(DATA / "cycles.json")
    cycles_js = read_js_payload(DATA / "cycles.js", "CYCLE_DATA")
    if cycles_js != cycles:
        fail(errors, "cycles.js payload differs from cycles.json")
    cycle_rows = cycles.get("cycles")
    if cycles.get("time_zone") != "UTC" or not isinstance(cycle_rows, list) or len(cycle_rows) != 14:
        fail(errors, "cycles.json must define 14 supplied UTC intervals")
    elif any(not all(isinstance(row.get(field), str) for field in ("Name", "ShortName", "StartDateTime", "EndDateTime")) for row in cycle_rows):
        fail(errors, "Each cycle interval requires Name, ShortName, StartDateTime, and EndDateTime strings")
    else:
        by_name = {row["Name"]: row for row in cycle_rows}
        if by_name.get("Phase 1", {}).get("StartDateTime") != "2022-12-06T12:00:00+00:00":
            fail(errors, "Cycle reference must identify the 6 December 2022 Phase 1 start")
        source_note = cycles.get("source_note", "")
        if "not server-availability windows" not in source_note or "24/7" not in source_note:
            fail(errors, "Cycle source note must distinguish Pre-era timelines from the Era 5 24/7 model")
        if by_name.get("Era 6, Cycle 6", {}).get("ShortName") != "e6c6":
            fail(errors, "Cycle reference must identify Era 6 Cycle 6 as e6c6")
        short_names = [row["ShortName"] for row in cycle_rows]
        if len(short_names) != len(set(short_names)):
            fail(errors, "Cycle reference short names must be unique")
        era6_cycles = [by_name.get(f"Era 6, Cycle {number}") for number in range(1, 7)]
        if any(not cycle or not cycle["StartDateTime"].endswith("T12:00:00+00:00") for cycle in era6_cycles):
            fail(errors, "Every Era 6 cycle must begin at the reviewed noon UTC boundary")
        if any(not cycle or not cycle["EndDateTime"].endswith("T12:00:00+00:00") for cycle in era6_cycles[:5]):
            fail(errors, "Every completed Era 6 cycle must end at the reviewed noon UTC boundary")
        cycle6 = by_name.get("Era 6, Cycle 6", {})
        if "Expected September 2026" not in cycle6.get("EndStatus", "") or "placeholder only" not in source_note:
            fail(errors, "Cycle 6 must describe its September 2026 end as unconfirmed, not open-ended")

    official_artifacts = read_json(DATA / "official_artifacts.json")
    artifact_rows = official_artifacts.get("artifacts", [])
    artifact_source = official_artifacts.get("source", {})
    if official_artifacts.get("schema_version") != 1 or not isinstance(artifact_rows, list) or len(artifact_rows) != 31:
        fail(errors, "Official artifact snapshot must preserve 31 supplied records")
    else:
        artifact_ids = [row.get("id") for row in artifact_rows]
        if len(artifact_ids) != len(set(artifact_ids)):
            fail(errors, "Official artifact IDs are not unique")
        for row in artifact_rows:
            if not all(isinstance(row.get(field), str) and row[field] for field in ("id", "title", "url", "type", "createdAt")):
                fail(errors, f"Official artifact record is incomplete: {row.get('id')}")
            if row.get("type") != "transmission" or row.get("published") is not True:
                fail(errors, f"Official artifact is not a published transmission: {row.get('id')}")
        if "not asserted to be the original broadcast publication time" not in artifact_source.get("created_at_note", ""):
            fail(errors, "Official artifact createdAt caveat is missing")
        official_index = read_js_payload(DATA / "official_artifacts.js", "OFFICIAL_ARTIFACT_INDEX")
        if set(official_index) != set(artifact_ids):
            fail(errors, "Official artifact browser index IDs differ from snapshot")
        else:
            for row in artifact_rows:
                indexed = official_index.get(row["id"], {})
                if indexed.get("url") != row["url"] or indexed.get("createdAt") != row["createdAt"]:
                    fail(errors, f"Official artifact browser index differs for {row['id']}")

    glyphs = catalogue.get("glyphs", [])
    glyph_ids = [int(glyph["id"]) for glyph in glyphs]
    if len(glyph_ids) != len(set(glyph_ids)):
        fail(errors, "Canonical glyph IDs are not unique")
    for glyph in glyphs:
        fingerprint = glyph.get("fingerprint", "")
        if len(fingerprint) != 81 or set(fingerprint) - {"0", "1"}:
            fail(errors, f"Glyph #{glyph.get('id')} has an invalid fingerprint")
        expected_indices = [index for index, bit in enumerate(fingerprint) if bit == "1"]
        if glyph.get("cell_indices") != expected_indices:
            fail(errors, f"Glyph #{glyph.get('id')} cell_indices differ from its fingerprint")

    occurrences = read_csv(DATA / "glyph_occurrences.csv")
    occurrence_keys = Counter(
        (row["recording"], int(row["ordinal"]), int(row["frame"]), int(row["glyph_id"]))
        for row in occurrences
    )
    if any(count != 1 for count in occurrence_keys.values()):
        fail(errors, "Occurrence identity tuples are not unique")
    unknown_occurrence_ids = sorted({int(row["glyph_id"]) for row in occurrences} - set(glyph_ids))
    if unknown_occurrence_ids:
        fail(errors, f"Occurrences reference unknown glyph IDs: {unknown_occurrence_ids}")

    stats = catalogue.get("stats", {})
    if stats.get("canonical_glyphs") != len(glyphs):
        fail(errors, "stats.canonical_glyphs does not match catalogue glyph count")
    if stats.get("occurrences") != len(occurrences):
        fail(errors, "stats.occurrences does not match occurrence CSV count")
    manual_count = sum(row["provisional"].lower() != "true" for row in occurrences)
    provisional_count = len(occurrences) - manual_count
    if stats.get("manual_occurrences") != manual_count:
        fail(errors, "stats.manual_occurrences does not match occurrence CSV")
    if stats.get("provisional_occurrences") != provisional_count:
        fail(errors, "stats.provisional_occurrences does not match occurrence CSV")

    sequences = read_csv(DATA / "sequences.csv")
    occurrence_counts = Counter(row["recording"] for row in occurrences)
    sequence_recordings = [row["recording"] for row in sequences]
    if len(sequence_recordings) != len(set(sequence_recordings)):
        fail(errors, "Sequence recording labels are not unique")
    if set(sequence_recordings) != set(occurrence_counts):
        fail(errors, "Sequence recordings differ from occurrence recordings")
    for row in sequences:
        if int(row["n_glyphs"]) != occurrence_counts[row["recording"]]:
            fail(errors, f"Sequence count differs for {row['recording']}")
        sequence_ids = [int(value) for value in row["glyph_ids"].split()]
        expected_ids = [
            int(item["glyph_id"])
            for item in sorted(
                (item for item in occurrences if item["recording"] == row["recording"]),
                key=lambda item: int(item["ordinal"]),
            )
        ]
        if sequence_ids != expected_ids:
            fail(errors, f"Sequence glyph IDs differ from occurrences for {row['recording']}")

    evidence = read_json(DATA / "evidence.json")
    evidence_js = read_js_payload(DATA / "evidence.js", "GLYPH_EVIDENCE")
    if evidence_js != evidence:
        fail(errors, "evidence.js payload differs from evidence.json")
    manifest = read_csv(DATA / "evidence_manifest.csv")
    if len(evidence) != len(manifest) or len(evidence) != len(occurrences):
        fail(errors, "Evidence JSON, manifest, and occurrence counts differ")

    evidence_keys = Counter(
        (row["recording"], int(row["ordinal"]), int(row["frame"]), int(row["glyph_id"]))
        for row in evidence
    )
    if evidence_keys != occurrence_keys:
        fail(errors, "Evidence records do not cover occurrence identity tuples exactly")

    evidence_ids = [row["evidence_id"] for row in evidence]
    image_paths = [row["image"] for row in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        fail(errors, "Evidence IDs are not unique")
    if len(image_paths) != len(set(image_paths)):
        fail(errors, "Evidence image paths are not unique per occurrence")
    for row in evidence:
        fingerprint = row.get("observed_fingerprint", "")
        canonical = row.get("canonical_fingerprint", "")
        if len(fingerprint) != 81 or set(fingerprint) - {"0", "1"}:
            fail(errors, f"{row['evidence_id']} has an invalid observed fingerprint")
        if len(canonical) != 81 or set(canonical) - {"0", "1"}:
            fail(errors, f"{row['evidence_id']} has an invalid canonical fingerprint")
        assigned = sum(left != right for left, right in zip(fingerprint, canonical))
        if int(row["assigned_hamming"]) != assigned:
            fail(errors, f"{row['evidence_id']} assigned_hamming is incorrect")
        if not row.get("source_video"):
            fail(errors, f"{row['evidence_id']} has no exact source filename")
        geometry = [row.get("overlay_center_x"), row.get("overlay_center_y"), row.get("overlay_pitch")]
        registration = row.get("overlay_registration")
        if registration not in {"detector-ring-fit", "unavailable"}:
            fail(errors, f"{row['evidence_id']} has an invalid QA-overlay registration method")
        if row.get("provisional"):
            if not all(isinstance(value, (int, float)) and value > 0 for value in geometry):
                fail(errors, f"{row['evidence_id']} has no detector QA-overlay geometry")
            if registration != "detector-ring-fit":
                fail(errors, f"{row['evidence_id']} provisional evidence must retain detector-ring registration")
        elif any(value is not None for value in geometry) or registration != "unavailable":
            fail(errors, f"{row['evidence_id']} manual evidence must not claim unrecorded QA-overlay geometry")
        image = ROOT / row["image"]
        if not image.is_file():
            fail(errors, f"Missing evidence image: {row['image']}")

    committed_images = sorted(path for path in (ROOT / "evidence").rglob("*.jpg") if "audits" not in path.parts)
    if len(committed_images) != len(evidence):
        fail(errors, "Committed evidence-image count differs from evidence records")

    review_path = DATA / "manual_geometry_review.json"
    if review_path.is_file():
        review_rows = read_json(review_path)
        manual_evidence = [row for row in evidence if not row.get("provisional")]
        review_keys = {(row.get("recording"), row.get("ordinal"), row.get("frame"), row.get("source_video")) for row in review_rows}
        manual_keys = {(row.get("recording"), row.get("ordinal"), row.get("frame"), row.get("source_video")) for row in manual_evidence}
        if review_keys != manual_keys:
            fail(errors, "Manual geometry review ledger does not cover manual evidence exactly")
        for row in review_rows:
            if row.get("review_status") != "pending" or row.get("overlay_enabled") is not False:
                fail(errors, "Manual geometry candidates must remain pending with overlays disabled")
            if not row.get("source_sha256") or not row.get("method"):
                fail(errors, "Manual geometry candidate lacks source identity or method")
            corpus = row.get("corpus_fingerprint", "")
            detected = row.get("detected_fingerprint", "")
            if len(corpus) != 81 or set(corpus) - {"0", "1"} or len(detected) != 81 or set(detected) - {"0", "1"}:
                fail(errors, "Manual detection backfill has an invalid fingerprint")
            distance = sum(left != right for left, right in zip(corpus, detected))
            if row.get("hamming_to_corpus") != distance:
                fail(errors, "Manual detection backfill has an invalid Hamming distance")
            expected_comparison = "exact support" if distance == 0 else "near support" if distance <= 2 else "disagreement"
            if row.get("comparison") != expected_comparison:
                fail(errors, "Manual detection backfill has an invalid comparison label")

    integrity = read_json(DATA / "source_integrity.json")
    integrity_rows = integrity.get("entries", [])
    if integrity.get("hash_algorithm") != "SHA-256" or not integrity_rows:
        fail(errors, "Source integrity manifest is empty or does not declare SHA-256")
    identities = [(row.get("source_set"), row.get("filename")) for row in integrity_rows]
    if len(identities) != len(set(identities)):
        fail(errors, "Source integrity identities are not unique")
    sha_pattern = re.compile(r"^[0-9a-f]{64}$")
    for row in integrity_rows:
        if not sha_pattern.fullmatch(str(row.get("sha256", ""))):
            fail(errors, f"Invalid source SHA-256: {row.get('source_set')}/{row.get('filename')}")
        if not isinstance(row.get("bytes"), int) or row["bytes"] <= 0:
            fail(errors, f"Invalid source byte count: {row.get('source_set')}/{row.get('filename')}")
    integrity_csv = read_csv(DATA / "source_integrity.csv")
    if len(integrity_csv) != len(integrity_rows):
        fail(errors, "Source integrity JSON/CSV counts differ")
    available_names = {row.get("filename") for row in integrity_rows}
    hashes_by_filename = {row.get("filename"): row.get("sha256") for row in integrity_rows}
    unknown_source_videos = sorted({row["source_video"] for row in evidence} - available_names)
    if unknown_source_videos:
        fail(errors, f"Evidence filenames absent from source integrity manifest: {unknown_source_videos}")

    vision_config_path = ROOT / "pipeline" / "vision_spike_config.json"
    vision_results_path = ROOT / "research" / "vision-registration-spike" / "results.json"
    hybrid_results_path = ROOT / "research" / "hybrid-registration-spike" / "results.json"
    if not vision_config_path.is_file() or not vision_results_path.is_file():
        fail(errors, "Vision registration spike is missing its config or committed results")
    else:
        vision_config = read_json(vision_config_path)
        vision_results = read_json(vision_results_path)
        checkpoint = vision_config.get("checkpoint", {})
        if not sha_pattern.fullmatch(str(checkpoint.get("sha256", ""))) or checkpoint.get("size_bytes", 0) <= 0:
            fail(errors, "Vision spike checkpoint identity is invalid")
        if vision_results.get("status") != "experimental-not-canonical":
            fail(errors, "Vision spike results must remain explicitly non-canonical")
        if vision_results.get("checkpoint", {}).get("sha256") != checkpoint.get("sha256"):
            fail(errors, "Vision spike config/results checkpoint hashes differ")
        for row in vision_results.get("results", []):
            if hashes_by_filename.get(row.get("source_video")) != row.get("source_sha256"):
                fail(errors, f"Vision spike source hash differs from integrity manifest: {row.get('source_video')}")
            if any(key in row for key in ("fingerprint", "glyph_id", "cell_values")):
                fail(errors, "Vision spike result improperly contains corpus-derived values")
            render = ROOT / "research" / "vision-registration-spike" / row.get("render", "")
            if not render.is_file():
                fail(errors, f"Missing vision spike render: {row.get('render')}")
        if not hybrid_results_path.is_file():
            fail(errors, "Hybrid registration spike is missing its committed results")
        else:
            hybrid_results = read_json(hybrid_results_path)
            if hybrid_results.get("status") != "experimental-not-canonical":
                fail(errors, "Hybrid registration results must remain explicitly non-canonical")
            if hybrid_results.get("checkpoint", {}).get("sha256") != checkpoint.get("sha256"):
                fail(errors, "Hybrid/config checkpoint hashes differ")
            hybrid_rows = hybrid_results.get("results", [])
            if len(hybrid_rows) != 8 or hybrid_results.get("summary", {}).get("pairs") != len(hybrid_rows):
                fail(errors, "Hybrid registration trial must retain all eight evaluated pairs")
            for row in hybrid_rows:
                if hashes_by_filename.get(row.get("source_video")) != row.get("source_sha256"):
                    fail(errors, f"Hybrid source hash differs from integrity manifest: {row.get('source_video')}")
                if any(key in row for key in ("fingerprint", "glyph_id", "cell_values", "overlay_enabled")):
                    fail(errors, "Hybrid result improperly contains corpus or promotion values")
                render = ROOT / "research" / "hybrid-registration-spike" / row.get("render", "")
                if not render.is_file():
                    fail(errors, f"Missing hybrid registration render: {row.get('render')}")
                if row.get("operational_consensus") and "manual review required" not in row.get("operational_status", ""):
                    fail(errors, "Hybrid candidate does not retain its manual-review requirement")

    audit = read_json(DATA / "disputed_cell_audit.json")
    audit_js = read_js_payload(DATA / "disputed_cell_audit.js", "GLYPH_CELL_AUDIT")
    if audit_js != audit:
        fail(errors, "disputed_cell_audit.js payload differs from disputed_cell_audit.json")
    if {row.get("cell") for row in audit.get("audits", [])} != {"(2,6)", "(5,2)"}:
        fail(errors, "Disputed-cell audit must cover (2,6) and (5,2)")
    audit_csv = read_csv(DATA / "disputed_cell_audit.csv")
    audit_source_count = sum(len(row.get("sources", [])) for row in audit.get("audits", []))
    if len(audit_csv) != audit_source_count:
        fail(errors, "Disputed-cell audit JSON/CSV source counts differ")
    integrity_hashes = {(row["source_set"], row["filename"]): row["sha256"] for row in integrity_rows}
    for row in audit.get("audits", []):
        for source in row.get("sources", []):
            key = (source.get("source_set"), source.get("source_video"))
            if integrity_hashes.get(key) != source.get("sha256"):
                fail(errors, f"Audit source hash differs from integrity manifest: {key}")
            image = ROOT / source.get("median_image", "")
            if not image.is_file():
                fail(errors, f"Missing disputed-cell median image: {source.get('median_image')}")

    e6c2_1k_sources = {
        row["source_video"] for row in evidence if row["recording"] == "E6C2-1K"
    }
    if e6c2_1k_sources != {"E6C2-1K zoomed.mp4"}:
        fail(errors, "E6C2-1K evidence must use E6C2-1K zoomed.mp4")

    manifest_ids = [row["evidence_id"] for row in manifest]
    if manifest_ids != evidence_ids:
        fail(errors, "Evidence manifest order/IDs differ from evidence.json")

    index_text = (ROOT / "index.html").read_text(encoding="utf-8")
    for reference in ("data/catalogue.js", "data/evidence.js", "data/disputed_cell_audit.js", "assets/release.js", "assets/app.js"):
        if reference not in index_text:
            fail(errors, f"index.html does not reference {reference}")
    if "data/official_artifacts.js" not in index_text or "data/official_artifacts.json" not in index_text:
        fail(errors, "Explorer does not expose official artifact provenance")
    for element_id in ("cell-heatmap", "cell-review", "cell-pattern-list", "cell-evidence-list"):
        if f'id="{element_id}"' not in index_text:
            fail(errors, f"index.html is missing Cell Activation element #{element_id}")
    if 'id="evidence-dialog-overlay"' not in index_text or 'id="evidence-dialog-source-caption"' not in index_text:
        fail(errors, "Explorer is missing the evidence QA overlay surface")
    repository_url = "https://github.com/Scetrov/eve-frontier-glyph-explorer"
    for element_id in ("report-glyph", "report-evidence", "report-cell"):
        if f'id="{element_id}"' not in index_text:
            fail(errors, f"index.html is missing issue-report link #{element_id}")
    if repository_url not in index_text:
        fail(errors, "Explorer does not link to its GitHub repository")
    if 'href="cycles.html"' not in index_text:
        fail(errors, "Explorer does not link to the cycle reference page")
    if 'id="release-commit"' not in index_text or "© 2026 SCETROV" not in index_text:
        fail(errors, "Footer must identify the current release link and Scetrov copyright")
    credits_text = (ROOT / "credits.html").read_text(encoding="utf-8")
    if "https://fenris.com/products" not in index_text or "https://fenris.com/products" not in credits_text:
        fail(errors, "Fenris Creations puzzle credit is missing from the explorer or credits page")
    if "fun mystery to investigate" not in index_text or "fun mystery to investigate" not in credits_text:
        fail(errors, "Fenris Creations puzzle acknowledgement is incomplete")
    if "Official artifact records" not in credits_text or "record creation time" not in credits_text:
        fail(errors, "Credits page does not explain official artifact provenance")

    app_text = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
    for behavior in ("selectCell", "renderCellReview", "createEvidenceCard", "createEvidenceImageStage", "drawEvidenceOverlay", "overlayGeometry", "officialArtifactFor", "officialArtifactMeta", "issueUrl", "glyphIssueBody", "frameIssueBody", "cellIssueBody"):
        if behavior not in app_text:
            fail(errors, f"assets/app.js is missing Cell Activation behavior {behavior}")

    release_text = (ROOT / "assets" / "release.js").read_text(encoding="utf-8")
    if "release-commit" not in release_text or "data/release.json" not in release_text:
        fail(errors, "assets/release.js must render the deployed commit link")
    cycles_page = ROOT / "cycles.html"
    if not cycles_page.is_file():
        fail(errors, "Missing cycle reference page")
    else:
        cycles_text = cycles_page.read_text(encoding="utf-8")
        for reference in ("data/cycles.js", "assets/cycles.js", "assets/release.js", 'id="cycle-table-body"'):
            if reference not in cycles_text:
                fail(errors, f"cycles.html is missing {reference}")
    cycle_script = (ROOT / "assets" / "cycles.js").read_text(encoding="utf-8")
    for behavior in ("CYCLE_DATA", "forEach", "noteFor", "cycle-table-body"):
        if behavior not in cycle_script:
            fail(errors, f"assets/cycles.js is missing cycle-reference behavior {behavior}")

    release = read_json(DATA / "release.json")
    if not isinstance(release.get("commit"), str) or not isinstance(release.get("short_commit"), str):
        fail(errors, "data/release.json must define commit and short_commit strings")
    pages_workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    if "Stamp deployed commit" not in pages_workflow or "data/release.json" not in pages_workflow:
        fail(errors, "Pages workflow does not stamp deployed commit metadata")

    template_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    expected_templates = {
        "glyph-report.md": "report: glyph",
        "frame-report.md": "report: frame",
        "cell-report.md": "report: cell",
    }
    for filename, label in expected_templates.items():
        path = template_dir / filename
        if not path.is_file():
            fail(errors, f"Missing issue template: .github/ISSUE_TEMPLATE/{filename}")
            continue
        template_text = path.read_text(encoding="utf-8")
        if not template_text.startswith("---\n") or label not in template_text:
            fail(errors, f"Issue template {filename} is missing frontmatter or label {label!r}")
    if not (template_dir / "config.yml").is_file():
        fail(errors, "Missing issue-template configuration")

    style_text = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    if 'font-family: "Disket Mono"' not in style_text:
        fail(errors, "Disket Mono @font-face declarations are missing")
    for token in ("--crude: #0b0b0b", "--martian-red: #ff4700", "--neutral: #fafae5"):
        if token not in style_text:
            fail(errors, f"Missing required colour token: {token}")
    for font_file in ("disket-mono-regular.woff2", "disket-mono-bold.woff2"):
        if not (ROOT / "assets" / "fonts" / font_file).is_file():
            fail(errors, f"Missing bundled font: assets/fonts/{font_file}")
    provenance_text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in ("SOURCES.md", "NOTICE.md", "credits.html")
    )
    if "https://rostype.com/disket/" not in provenance_text or "void-eid" in provenance_text:
        fail(errors, "Disket Mono provenance must identify Rostype and must not identify void-eid")

    pipeline_files = (
        "pipeline/corpus.json", "pipeline/requirements.txt", "pipeline/requirements-vision-spike.txt", "pipeline/README.md",
        "pipeline/common.py", "pipeline/analyze_sources.py", "pipeline/build_site.py", "pipeline/run_pipeline.py",
        "pipeline/inventory_sources.py", "pipeline/audit_disputed_cells.py", "pipeline/vision_registration_spike.py",
        "pipeline/hybrid_registration_spike.py",
    )
    for relative in pipeline_files:
        if not (ROOT / relative).is_file():
            fail(errors, f"Missing end-to-end pipeline file: {relative}")
    try:
        config = read_json(ROOT / "pipeline" / "corpus.json")
        if config.get("manual_source_overrides", {}).get("E6C2-1K") != "E6C2-1K zoomed.mp4":
            fail(errors, "pipeline/corpus.json does not enforce the E6C2-1K source override")
        automatic = config.get("automatic_sources", [])
        labels = [item.get("broadcast") for item in automatic]
        filenames = [item.get("file") for item in automatic]
        if len(labels) != len(set(labels)) or not all(labels) or not all(filenames):
            fail(errors, "pipeline/corpus.json has invalid automatic source identities")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        fail(errors, f"Invalid pipeline/corpus.json: {error}")

    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    if "all-github-actions:" not in dependabot or not re.search(r"patterns:\s*\n\s*-\s*[\"']?\*[\"']?", dependabot):
        fail(errors, "Dependabot does not group all GitHub Actions updates")

    skill_count = validate_skills(errors)

    summary = {
        "glyphs": len(glyphs),
        "occurrences": len(occurrences),
        "manual_occurrences": manual_count,
        "provisional_occurrences": provisional_count,
        "recordings": len(sequences),
        "evidence_records": len(evidence),
        "evidence_images": len(committed_images),
        "skills": skill_count,
        "errors": errors,
    }
    print(json.dumps(summary, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
