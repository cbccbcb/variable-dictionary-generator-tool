#!/usr/bin/env python3
"""Merge JSONL files or a directory of JSONL batches into one JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def input_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.jsonl")))
        else:
            files.append(path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dedupe-key", default="")
    args = parser.parse_args()

    seen = set()
    count = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for path in input_files(args.inputs):
            with path.open("r", encoding="utf-8-sig") as f:
                for line_no, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise SystemExit(f"Invalid JSON in {path}:{line_no}: {exc}") from exc
                    if args.dedupe_key:
                        key = obj.get(args.dedupe_key)
                        if key in seen:
                            continue
                        seen.add(key)
                    out.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    count += 1
    print(f"Wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
