#!/usr/bin/env python3
"""Index variable-derivation signals from a remote GitHub or GitLab repository."""

from __future__ import annotations

import argparse
import ast
import json
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


INCLUDE_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".json", ".toml", ".csv"}
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
    ".nexus-map",
}
MAX_DEFAULT_FILE_BYTES = 250_000
DEFAULT_TOP_CANDIDATES = 50
DEFAULT_MAX_DEPENDENCY_FILES = 100


PYTHON_PATTERNS = [
    (
        "dataframe_assignment",
        re.compile(
            r"""(?:df|data|features|feature|out|result|res|X|dataset|base|agg|tmp)\s*\[\s*(?:[furbFURB]*)?['"]([^'"]+)['"]\s*\]\s*="""
        ),
    ),
    ("with_column", re.compile(r"""\.withColumn\(\s*['"]([^'"]+)['"]""")),
    ("with_columns_alias", re.compile(r"""\.alias\(\s*['"]([^'"]+)['"]\s*\)""")),
    ("assign_keyword", re.compile(r"""\.assign\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*=""")),
    ("assign_dict_unpack", re.compile(r"""(?:assign|update)\(\s*\*\*\s*\{[^}]*['"]([^'"]+)['"]\s*:""", re.DOTALL)),
    (
        "dict_key_assignment",
        re.compile(r"""(?:features|out|result|res|feature_dict|feature_map)\s*\[\s*(?:[furbFURB]*)?['"]([^'"]+)['"]\s*\]\s*="""),
    ),
    ("dict_literal_key", re.compile(r"""['"]([A-Za-z_][A-Za-z0-9_]*(?:_\{[^}]+\})?[A-Za-z0-9_]*)['"]\s*:""")),
    ("named_agg_keyword", re.compile(r"""([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:pd\.)?NamedAgg\(""")),
    ("agg_named_tuple", re.compile(r"""([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(\s*['"][^'"]+['"]\s*,\s*['"][^'"]+['"]\s*\)""")),
    ("rename_columns", re.compile(r"""\.rename\(\s*columns\s*=\s*\{[^}]*['"][^'"]+['"]\s*:\s*['"]([^'"]+)['"]""", re.DOTALL)),
    ("select_expr_alias", re.compile(r"""(?i)(?:selectExpr|expr)\([^)]*\bAS\s+([A-Za-z_][A-Za-z0-9_]*)""")),
]
CONFIG_FEATURE_PATTERNS = [
    ("config_name", re.compile(r"""(?im)^\s*(?:name|feature|feature_name|variable|variable_name|alias|output|output_name)\s*:\s*['"]?([A-Za-z_][A-Za-z0-9_{}]*)['"]?\s*$""")),
    ("config_list_item", re.compile(r"""(?im)^\s*-\s*['"]?([A-Za-z_][A-Za-z0-9_{}]*(?:_\d+[dmy])?)['"]?\s*$""")),
    ("json_feature_key", re.compile(r"""(?i)['"](?:name|feature|feature_name|variable|variable_name|alias|output|output_name)['"]\s*:\s*['"]([^'"]+)['"]""")),
]
SQL_ALIAS_PATTERN = re.compile(r"""\bAS\s+[`"[]?([A-Za-z_][A-Za-z0-9_{}]*)[`"\]]?""", re.IGNORECASE)
SQL_INTO_PATTERN = re.compile(r"""(?i)\b(?:CREATE\s+TABLE|INSERT\s+INTO)\s+([A-Za-z_][A-Za-z0-9_.]*)""")
TIME_WINDOW_PATTERN = re.compile(r"""(?i)(\b\d+\s*[dmy]\b|\b\d+\s*day\b|\b\d+\s*days\b|rolling\s*\(|window\s*\(|interval\s+['"]?\d+)""")
AGG_PATTERN = re.compile(r"""(?i)\b(groupby|group\s+by|pivot_table|crosstab|resample|over\s*\(|partition\s+by|count|sum|avg|mean|max|min|median|rolling|expanding|ewm|rank|nunique|distinct|std|var|quantile)\b""")
JOIN_PATTERN = re.compile(r"""(?i)\b(join|merge|concat)\b|\.merge\(""")
FILTER_PATTERN = re.compile(r"""(?i)\b(where|filter|query|between|case\s+when|when\s*\(|otherwise\s*\(|>=|<=|==|!=)\b""")
FEATURE_NAME_PATTERN = re.compile(r"""(?i)(feature|features|variable|variables|indicator|metric|factor|derive|derived|transform|pipeline|score|risk|label|etl)""")
PATH_REFERENCE_PATTERN = re.compile(r"""['"]([^'"]+\.(?:py|sql|yaml|yml|json|toml|csv))['"]""", re.IGNORECASE)
HELPER_FILE_PATTERN = re.compile(r"""(?i)(common|config|configs|setting|settings|window|windows|date|time|util|utils|mapping|map|field|fields|column|columns|schema|sql)""")


@dataclass(frozen=True)
class RepoSpec:
    provider: str
    host: str
    owner: str
    repo: str
    project_path: str


def request_json(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
    except URLError as exc:
        raise SystemExit(f"Network error for {url}: {exc}") from exc


def request_bytes(url: str, headers: dict[str, str]) -> bytes:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
    except URLError as exc:
        raise SystemExit(f"Network error for {url}: {exc}") from exc


def parse_repo_url(repo_url: str, provider: str | None) -> RepoSpec:
    parsed = urlparse(repo_url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("repo_url must be an HTTP(S) GitHub or GitLab repository URL")

    host = parsed.netloc
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise SystemExit("repo_url must include owner/group and repository name")

    inferred = provider
    if inferred is None:
        if "github" in host:
            inferred = "github"
        elif "gitlab" in host:
            inferred = "gitlab"
        else:
            raise SystemExit("Use --provider for non-standard GitHub/GitLab hosts")

    if inferred == "github":
        owner, repo = parts[0], parts[1]
        project_path = f"{owner}/{repo}"
    elif inferred == "gitlab":
        owner, repo = "/".join(parts[:-1]), parts[-1]
        project_path = "/".join(parts)
    else:
        raise SystemExit("--provider must be github or gitlab")

    return RepoSpec(provider=inferred, host=host, owner=owner, repo=repo, project_path=project_path)


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "variable-dictionary-generator-tool",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def gitlab_headers() -> dict[str, str]:
    headers = {"User-Agent": "variable-dictionary-generator-tool"}
    token = os.getenv("GITLAB_TOKEN")
    if token:
        headers["PRIVATE-TOKEN"] = token
    return headers


def github_api_base(spec: RepoSpec) -> str:
    if spec.host == "github.com":
        return "https://api.github.com"
    return f"https://{spec.host}/api/v3"


def gitlab_api_base(spec: RepoSpec) -> str:
    if spec.host == "gitlab.com":
        return "https://gitlab.com/api/v4"
    return f"https://{spec.host}/api/v4"


def github_default_branch(spec: RepoSpec, headers: dict[str, str]) -> str:
    data = request_json(f"{github_api_base(spec)}/repos/{spec.project_path}", headers)
    return str(data.get("default_branch") or "main")


def gitlab_default_branch(spec: RepoSpec, headers: dict[str, str]) -> str:
    encoded_project = quote(spec.project_path, safe="")
    data = request_json(f"{gitlab_api_base(spec)}/projects/{encoded_project}", headers)
    return str(data.get("default_branch") or "main")


def github_tree(spec: RepoSpec, branch: str, headers: dict[str, str]) -> tuple[list[dict[str, Any]], bool]:
    url = f"{github_api_base(spec)}/repos/{spec.project_path}/git/trees/{quote(branch, safe='')}?recursive=1"
    data = request_json(url, headers)
    tree = data.get("tree", [])
    return tree, bool(data.get("truncated"))


def gitlab_tree(spec: RepoSpec, branch: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    encoded_project = quote(spec.project_path, safe="")
    encoded_ref = quote(branch, safe="")
    base = f"{gitlab_api_base(spec)}/projects/{encoded_project}/repository/tree"
    page = 1
    rows: list[dict[str, Any]] = []
    while True:
        url = f"{base}?recursive=true&ref={encoded_ref}&per_page=100&page={page}"
        batch = request_json(url, headers)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return rows


def github_file_bytes(spec: RepoSpec, path: str, branch: str, headers: dict[str, str]) -> bytes:
    raw_headers = dict(headers)
    raw_headers["Accept"] = "application/vnd.github.raw"
    url = f"{github_api_base(spec)}/repos/{spec.project_path}/contents/{quote(path)}?ref={quote(branch, safe='')}"
    return request_bytes(url, raw_headers)


def gitlab_file_bytes(spec: RepoSpec, sha: str, headers: dict[str, str]) -> bytes:
    encoded_project = quote(spec.project_path, safe="")
    url = f"{gitlab_api_base(spec)}/projects/{encoded_project}/repository/blobs/{sha}/raw"
    return request_bytes(url, headers)


def is_excluded(path: str, extra_excludes: set[str]) -> bool:
    parts = set(path.split("/"))
    return bool(parts & (EXCLUDE_DIRS | extra_excludes))


def suffix_for(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def line_window(lines: list[str], line_no: int, radius: int = 2) -> str:
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start - 1 : end])


def line_slice(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def extract_python_symbols(text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    except Exception:
        return []

    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(
                {
                    "name": node.name,
                    "type": "class" if isinstance(node, ast.ClassDef) else "function",
                    "line_start": getattr(node, "lineno", None),
                    "line_end": getattr(node, "end_lineno", None),
                }
            )
    return sorted(symbols, key=lambda row: (row.get("line_start") or 0, row.get("line_end") or 0))


def python_symbol_chunks(path: str, text: str) -> list[dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    chunks: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if not start or not end:
                continue
            symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                {
                    "chunk_id": f"{path}::{symbol_type}::{node.name}::{start}-{end}",
                    "file": path,
                    "language": "python",
                    "symbol_type": symbol_type,
                    "symbol_name": node.name,
                    "start_line": start,
                    "end_line": end,
                    "code": line_slice(lines, start, end),
                }
            )
    return sorted(chunks, key=lambda row: (row["start_line"], row["end_line"]))


def fixed_size_chunks(path: str, text: str, language: str, max_lines: int) -> list[dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    chunks = []
    for idx, start in enumerate(range(1, len(lines) + 1, max_lines), start=1):
        end = min(start + max_lines - 1, len(lines))
        chunks.append(
            {
                "chunk_id": f"{path}::chunk::{idx:04d}::{start}-{end}",
                "file": path,
                "language": language,
                "symbol_type": "chunk",
                "symbol_name": f"chunk_{idx:04d}",
                "start_line": start,
                "end_line": end,
                "code": line_slice(lines, start, end),
            }
        )
    return chunks


def chunks_for_text(path: str, text: str, max_lines: int) -> list[dict[str, Any]]:
    language = language_for_path(path)
    if language == "python":
        chunks = python_symbol_chunks(path, text)
        if chunks:
            return chunks
    return fixed_size_chunks(path, text, language, max_lines)


def module_candidates(module_name: str) -> list[str]:
    path = module_name.replace(".", "/")
    return [f"{path}.py", f"{path}/__init__.py"]


def resolve_relative_module(path: str, module: str | None, level: int) -> list[str]:
    current_dir = posixpath.dirname(path)
    current_parts = [] if not current_dir else current_dir.split("/")
    if level <= 0:
        prefix_parts: list[str] = []
    else:
        keep = max(0, len(current_parts) - level + 1)
        prefix_parts = current_parts[:keep]

    module_parts = [] if not module else module.split(".")
    full_module = ".".join(prefix_parts + module_parts)
    return module_candidates(full_module) if full_module else []


def extract_import_references(path: str, text: str) -> set[str]:
    if suffix_for(path) != ".py":
        return set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.update(module_candidates(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                refs.update(resolve_relative_module(path, node.module, node.level))
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    module = ".".join(part for part in (node.module, alias.name) if part)
                    refs.update(resolve_relative_module(path, module, node.level))
            elif node.module:
                refs.update(module_candidates(node.module))
                for alias in node.names:
                    if alias.name != "*":
                        refs.update(module_candidates(f"{node.module}.{alias.name}"))
    return refs


def extract_path_references(path: str, text: str) -> set[str]:
    current_dir = posixpath.dirname(path)
    refs = set()
    for match in PATH_REFERENCE_PATTERN.finditer(text):
        value = match.group(1).strip()
        if value.startswith(("http://", "https://", "s3://")):
            continue
        refs.add(posixpath.normpath(value))
        if current_dir:
            refs.add(posixpath.normpath(posixpath.join(current_dir, value)))
    return refs


def sibling_helper_references(path: str, all_paths: set[str]) -> set[str]:
    current_dir = posixpath.dirname(path)
    if not current_dir:
        return set()
    refs = set()
    for candidate in all_paths:
        if posixpath.dirname(candidate) != current_dir or candidate == path:
            continue
        name = posixpath.basename(candidate)
        if HELPER_FILE_PATTERN.search(name):
            refs.add(candidate)
    return refs


def dependency_references(row: dict[str, Any], all_paths: set[str]) -> dict[str, set[str]]:
    path = row["path"]
    text = row.get("_text", "")
    return {
        "import": extract_import_references(path, text),
        "path_reference": extract_path_references(path, text),
        "sibling_helper": sibling_helper_references(path, all_paths),
    }


def extract_signals(path: str, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    candidate_variables: list[str] = []
    signals: list[dict[str, Any]] = []
    suffix = suffix_for(path)

    if suffix == ".py":
        for line_no, line in enumerate(lines, start=1):
            for signal_type, pattern in PYTHON_PATTERNS:
                for match in pattern.finditer(line):
                    variable = match.group(1)
                    candidate_variables.append(variable)
                    signals.append(
                        {
                            "type": signal_type,
                            "line": line_no,
                            "value": variable,
                            "snippet": line_window(lines, line_no),
                        }
                    )
    elif suffix == ".sql":
        for line_no, line in enumerate(lines, start=1):
            for match in SQL_ALIAS_PATTERN.finditer(line):
                variable = match.group(1)
                candidate_variables.append(variable)
                signals.append(
                    {
                        "type": "sql_alias",
                        "line": line_no,
                        "value": variable,
                            "snippet": line_window(lines, line_no),
                        }
                    )
            for match in SQL_INTO_PATTERN.finditer(line):
                target = match.group(1)
                signals.append(
                    {
                        "type": "sql_output_table",
                        "line": line_no,
                        "value": target,
                        "snippet": line_window(lines, line_no),
                    }
                )
    elif suffix in {".yaml", ".yml", ".json", ".toml", ".csv"}:
        for signal_type, pattern in CONFIG_FEATURE_PATTERNS:
            for match in pattern.finditer(text):
                variable = match.group(1)
                candidate_variables.append(variable)
                signals.append(
                    {
                        "type": signal_type,
                        "line": None,
                        "value": variable,
                    }
                )

    full_text = "\n".join(lines)
    if AGG_PATTERN.search(full_text):
        signals.append({"type": "aggregation", "line": None, "value": "aggregation/grouping pattern"})
    if TIME_WINDOW_PATTERN.search(full_text):
        signals.append({"type": "time_window", "line": None, "value": "time-window pattern"})
    if JOIN_PATTERN.search(full_text):
        signals.append({"type": "join", "line": None, "value": "join/merge pattern"})
    if FILTER_PATTERN.search(full_text):
        signals.append({"type": "filter", "line": None, "value": "filter condition pattern"})

    unique_variables = sorted(set(candidate_variables))
    path_bonus = 2 if FEATURE_NAME_PATTERN.search(path) else 0
    score = min(1.0, (len(unique_variables) * 0.08) + (len(signals) * 0.03) + (path_bonus * 0.1))
    reasons = []
    if unique_variables:
        reasons.append(f"found {len(unique_variables)} candidate variable names")
    if path_bonus:
        reasons.append("path contains feature/metric/indicator-like keyword")
    for signal_name in ("aggregation", "time_window", "join", "filter"):
        if any(signal["type"] == signal_name for signal in signals):
            reasons.append(f"contains {signal_name} signal")

    return {
        "candidate_score": round(score, 3),
        "is_candidate_feature_file": score >= 0.18,
        "candidate_variables": unique_variables,
        "signals": signals[:80],
        "reasons": reasons,
        "symbols": extract_python_symbols(text) if suffix == ".py" else [],
    }


def normalize_github_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "blob":
        return None
    return {
        "path": item.get("path", ""),
        "sha": item.get("sha", ""),
        "size": int(item.get("size") or 0),
    }


def normalize_gitlab_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "blob":
        return None
    return {
        "path": item.get("path", ""),
        "sha": item.get("id", ""),
        "size": int(item.get("size") or 0),
    }


def select_chunk_files(indexed_files: list[dict[str, Any]], scope: str, top_candidates: int) -> list[dict[str, Any]]:
    if scope == "all":
        return indexed_files

    candidates = [row for row in indexed_files if row["is_candidate_feature_file"]]
    candidates = sorted(
        candidates,
        key=lambda row: (row["candidate_score"], len(row["candidate_variables"]), -len(row["path"])),
        reverse=True,
    )
    if top_candidates > 0:
        return candidates[:top_candidates]
    return candidates


def expand_with_dependencies(
    selected_files: list[dict[str, Any]],
    indexed_files: list[dict[str, Any]],
    max_depth: int,
    max_dependency_files: int,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if max_depth <= 0 or max_dependency_files <= 0:
        return selected_files, {}

    rows_by_path = {row["path"]: row for row in indexed_files}
    all_paths = set(rows_by_path)
    selected_paths = {row["path"] for row in selected_files}
    include_reasons: dict[str, list[str]] = {path: ["selected candidate file"] for path in selected_paths}
    queue = [(row, 0) for row in selected_files]
    dependency_count = 0

    while queue and dependency_count < max_dependency_files:
        row, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        refs_by_type = dependency_references(row, all_paths)
        for reason_type, refs in refs_by_type.items():
            for ref in sorted(refs):
                if ref not in rows_by_path or ref in selected_paths:
                    continue
                selected_paths.add(ref)
                dependency_count += 1
                include_reasons.setdefault(ref, []).append(f"{reason_type} referenced by {row['path']}")
                queue.append((rows_by_path[ref], depth + 1))
                if dependency_count >= max_dependency_files:
                    break
            if dependency_count >= max_dependency_files:
                break

    expanded = [row for row in indexed_files if row["path"] in selected_paths]
    return expanded, include_reasons


def build_index(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = parse_repo_url(args.repo_url, args.provider)
    headers = github_headers() if spec.provider == "github" else gitlab_headers()
    branch = args.branch
    if not branch:
        branch = github_default_branch(spec, headers) if spec.provider == "github" else gitlab_default_branch(spec, headers)

    if spec.provider == "github":
        raw_tree, truncated = github_tree(spec, branch, headers)
        tree = [row for item in raw_tree if (row := normalize_github_item(item))]
    else:
        raw_tree = gitlab_tree(spec, branch, headers)
        truncated = False
        tree = [row for item in raw_tree if (row := normalize_gitlab_item(item))]

    extra_excludes = {part.strip() for part in args.exclude_dirs.split(",") if part.strip()}
    files = []
    skipped = {"excluded": 0, "suffix": 0, "large": 0, "limit": 0}
    for item in tree:
        path = item["path"]
        if is_excluded(path, extra_excludes):
            skipped["excluded"] += 1
            continue
        if suffix_for(path) not in INCLUDE_SUFFIXES:
            skipped["suffix"] += 1
            continue
        if item["size"] and item["size"] > args.max_file_bytes:
            skipped["large"] += 1
            continue
        files.append(item)

    files = sorted(files, key=lambda row: row["path"])
    if args.max_files and len(files) > args.max_files:
        skipped["limit"] = len(files) - args.max_files
        files = files[: args.max_files]

    indexed_files = []
    for item in files:
        if spec.provider == "github":
            data = github_file_bytes(spec, item["path"], branch, headers)
        else:
            data = gitlab_file_bytes(spec, item["sha"], headers)
        text = decode_text(data)
        signals = extract_signals(item["path"], text)
        indexed_files.append(
            {
                "path": item["path"],
                "language": language_for_path(item["path"]),
                "size": item["size"] or len(data),
                "sha": item["sha"],
                "_text": text,
                **signals,
            }
        )

    candidate_files = [row for row in indexed_files if row["is_candidate_feature_file"]]
    chunk_source_files = select_chunk_files(indexed_files, args.chunks_scope, args.top_candidates) if args.chunks_out else []
    include_reasons: dict[str, list[str]] = {}
    if args.chunks_out and args.include_dependencies and args.chunks_scope == "candidates":
        chunk_source_files, include_reasons = expand_with_dependencies(
            chunk_source_files,
            indexed_files,
            args.dependency_depth,
            args.max_dependency_files,
        )
    else:
        include_reasons = {row["path"]: ["selected for chunking"] for row in chunk_source_files}

    chunk_source_paths = {row["path"] for row in chunk_source_files}
    chunks: list[dict[str, Any]] = []
    for row in chunk_source_files:
        chunks.extend(chunks_for_text(row["path"], row["_text"], args.chunk_max_lines))

    public_files = []
    for row in indexed_files:
        public_row = dict(row)
        public_row.pop("_text", None)
        public_row["included_in_chunks"] = row["path"] in chunk_source_paths
        public_row["chunk_include_reasons"] = include_reasons.get(row["path"], [])
        public_files.append(public_row)

    index = {
        "schema_version": "derivation_index.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "url": args.repo_url,
            "provider": spec.provider,
            "host": spec.host,
            "project_path": spec.project_path,
            "branch": branch,
        },
        "scan_options": {
            "include_suffixes": sorted(INCLUDE_SUFFIXES),
            "exclude_dirs": sorted(EXCLUDE_DIRS | extra_excludes),
            "max_file_bytes": args.max_file_bytes,
            "max_files": args.max_files,
            "chunks_scope": args.chunks_scope if args.chunks_out else None,
            "top_candidates": args.top_candidates if args.chunks_out else None,
            "chunk_max_lines": args.chunk_max_lines if args.chunks_out else None,
            "include_dependencies": args.include_dependencies if args.chunks_out else None,
            "dependency_depth": args.dependency_depth if args.chunks_out else None,
            "max_dependency_files": args.max_dependency_files if args.chunks_out else None,
        },
        "summary": {
            "tree_file_count": len(tree),
            "indexed_file_count": len(indexed_files),
            "candidate_file_count": len(candidate_files),
            "candidate_variable_count": sum(len(row["candidate_variables"]) for row in indexed_files),
            "chunked_file_count": len(chunk_source_files),
            "chunk_count": len(chunks),
            "dependency_chunked_file_count": sum(
                1
                for row in chunk_source_files
                if row["path"] in include_reasons and "selected candidate file" not in include_reasons[row["path"]]
            ),
            "github_tree_truncated": truncated,
            "skipped": skipped,
        },
        "files": public_files,
    }
    return index, chunks


def language_for_path(path: str) -> str:
    suffix = suffix_for(path)
    return {
        ".py": "python",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".csv": "csv",
    }.get(suffix, suffix.lstrip(".") or "text")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_url", help="GitHub or GitLab repository URL")
    parser.add_argument("--provider", choices=["github", "gitlab"], help="Override provider detection")
    parser.add_argument("--branch", help="Branch or ref. Defaults to the repository default branch.")
    parser.add_argument("--out", required=True, help="Output derivation_index.json path")
    parser.add_argument("--exclude-dirs", default="", help="Comma-separated extra directory names to exclude")
    parser.add_argument("--max-file-bytes", type=int, default=MAX_DEFAULT_FILE_BYTES)
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--chunks-out", help="Optional JSONL output for remote code chunks")
    parser.add_argument(
        "--chunks-scope",
        choices=["candidates", "all"],
        default="candidates",
        help="Which indexed files to chunk when --chunks-out is set",
    )
    parser.add_argument(
        "--top-candidates",
        type=int,
        default=DEFAULT_TOP_CANDIDATES,
        help="Number of highest-scoring candidate files to chunk. Use 0 for all candidates.",
    )
    parser.add_argument("--chunk-max-lines", type=int, default=180)
    parser.add_argument(
        "--include-dependencies",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include one-hop imports, explicit path references, and sibling helper files when chunking candidates.",
    )
    parser.add_argument("--dependency-depth", type=int, default=1, help="Dependency expansion depth for candidate chunks")
    parser.add_argument("--max-dependency-files", type=int, default=DEFAULT_MAX_DEPENDENCY_FILES)
    args = parser.parse_args()

    index, chunks = build_index(args)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    chunks_path = None
    if args.chunks_out:
        chunks_path = os.path.abspath(args.chunks_out)
        os.makedirs(os.path.dirname(chunks_path), exist_ok=True)
        with open(chunks_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    summary = index["summary"]
    print(
        "Wrote derivation index to "
        f"{out_path}: {summary['indexed_file_count']} files, "
        f"{summary['candidate_file_count']} candidate files, "
        f"{summary['candidate_variable_count']} candidate variables"
    )
    if chunks_path:
        print(f"Wrote {summary['chunk_count']} remote code chunks from {summary['chunked_file_count']} files to {chunks_path}")
    if summary.get("github_tree_truncated"):
        print("Warning: GitHub tree response was truncated; narrow the scan or use a smaller target.", file=sys.stderr)


if __name__ == "__main__":
    main()
