#!/usr/bin/env python3
"""Validate final variable lineage CSV and optional lineage facts JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_COLUMNS = [
    "feature",
    "source_module",
    "feature_name",
    "time_window_cn",
    "indicator_level1_category_cn",
    "indicator_level2_category_cn",
    "indicator_category_cn",
    "source_function_cn",
    "input_data_cn",
    "processing_logic_cn",
    "calculation_logic_cn",
    "lineage_summary_cn",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    if fieldnames != REQUIRED_COLUMNS:
        raise SystemExit(
            "CSV header mismatch. Expected: "
            + ",".join(REQUIRED_COLUMNS)
            + " Got: "
            + ",".join(fieldnames)
        )
    return rows


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON in {path}:{line_no}: {exc}") from exc
    return rows


def validate(rows: list[dict[str, str]], facts: list[dict] | None) -> dict:
    issues = []
    features = [row.get("feature", "") for row in rows]
    duplicate_features = sorted({feature for feature in features if features.count(feature) > 1})
    if duplicate_features:
        issues.append({"severity": "high", "issue": "duplicate feature values", "features": duplicate_features[:20]})

    for idx, row in enumerate(rows, start=2):
        for column in REQUIRED_COLUMNS:
            value = (row.get(column) or "").strip()
            if not value:
                issues.append({"severity": "high", "issue": "empty required field", "row": idx, "column": column})

    if facts is not None:
        fact_features = [str(row.get("feature", "")) for row in facts]
        missing_in_csv = sorted(set(fact_features) - set(features))
        extra_in_csv = sorted(set(features) - set(fact_features))
        if missing_in_csv:
            issues.append({"severity": "high", "issue": "facts features missing in CSV", "features": missing_in_csv[:20]})
        if extra_in_csv:
            issues.append({"severity": "medium", "issue": "CSV features not present in facts", "features": extra_in_csv[:20]})
        no_evidence = [
            row.get("feature", "")
            for row in facts
            if not row.get("evidence_chunk_id") or not row.get("evidence_snippet")
        ]
        if no_evidence:
            issues.append({"severity": "medium", "issue": "facts rows missing evidence", "features": no_evidence[:20]})

    return {
        "row_count": len(rows),
        "unique_feature_count": len(set(features)),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    rows = read_csv(args.csv_path)
    facts = read_jsonl(args.facts) if args.facts else None
    report = validate(rows, facts)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(issue["severity"] == "high" for issue in report["issues"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
