#!/usr/bin/env python3
"""Scan source files and emit lightweight code chunks for LLM analysis."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


INCLUDE_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".json", ".toml"}
EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "output",
    "outputs",
}


def iter_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files: list[Path] = []
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in item.parts):
            continue
        if item.suffix.lower() in INCLUDE_SUFFIXES:
            files.append(item)
    return sorted(files)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def line_slice(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def python_symbol_chunks(path: Path, rel: str, text: str) -> list[dict]:
    lines = text.splitlines(keepends=True)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    chunks: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if not start or not end:
                continue
            symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                {
                    "chunk_id": f"{rel}::{symbol_type}::{node.name}::{start}-{end}",
                    "file": rel,
                    "language": "python",
                    "symbol_type": symbol_type,
                    "symbol_name": node.name,
                    "start_line": start,
                    "end_line": end,
                    "code": line_slice(lines, start, end),
                }
            )
    return sorted(chunks, key=lambda c: (c["start_line"], c["end_line"]))


def fixed_size_chunks(path: Path, rel: str, text: str, language: str, max_lines: int) -> list[dict]:
    lines = text.splitlines(keepends=True)
    chunks = []
    for idx, start in enumerate(range(1, len(lines) + 1, max_lines), start=1):
        end = min(start + max_lines - 1, len(lines))
        chunks.append(
            {
                "chunk_id": f"{rel}::chunk::{idx:04d}::{start}-{end}",
                "file": rel,
                "language": language,
                "symbol_type": "chunk",
                "symbol_name": f"chunk_{idx:04d}",
                "start_line": start,
                "end_line": end,
                "code": line_slice(lines, start, end),
            }
        )
    return chunks


def chunks_for_file(path: Path, root: Path, max_lines: int) -> list[dict]:
    rel = path.relative_to(root).as_posix() if root.is_dir() else path.name
    text = read_text(path)
    suffix = path.suffix.lower()
    if suffix == ".py":
        chunks = python_symbol_chunks(path, rel, text)
        if chunks:
            return chunks
        return fixed_size_chunks(path, rel, text, "python", max_lines)
    language = {
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
    }.get(suffix, suffix.lstrip(".") or "text")
    return fixed_size_chunks(path, rel, text, language, max_lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("code_path", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-lines", type=int, default=180)
    args = parser.parse_args()

    root = args.code_path.resolve()
    files = iter_files(root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.out.open("w", encoding="utf-8") as f:
        for file_path in files:
            for chunk in chunks_for_file(file_path, root, args.max_lines):
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total += 1
    print(f"Wrote {total} chunks from {len(files)} files to {args.out}")


if __name__ == "__main__":
    main()
