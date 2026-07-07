# Variable Dictionary Generator Tool

`variable-dictionary-generator-tool` is a Codex skill tool for generating
Chinese variable dictionaries and variable lineage documentation from feature
engineering source code.

It scans Python, SQL, and configuration files to identify variable generation
logic, input data, filters, grouping rules, time windows, calculation methods,
and business categories. The output is a structured, evidence-backed Chinese
CSV dictionary that can be used for feature governance, model audit, risk
analytics documentation, and data asset management.

Core capabilities:

- Scan and chunk source code into `code_chunks.jsonl`.
- Index remote GitHub/GitLab repositories without cloning the repo locally.
- Extract evidence-backed variable lineage facts from code.
- Support `quick`, `standard`, and `deep` workflow modes.
- Generate strict Chinese CSV output with fixed dictionary columns.
- Validate required fields, duplicate variables, and evidence coverage.
- Handle multi-file projects, dynamic variable names, SQL aliases, and
  configuration-driven feature generation.

## Structure

- `SKILL.md`: skill instructions and operating workflow.
- `scripts/index_remote_repo.py`: indexes variable-derivation signals from GitHub/GitLab URLs.
- `scripts/scan_codebase.py`: scans and chunks source files.
- `scripts/merge_jsonl.py`: merges JSONL batch outputs.
- `scripts/validate_lineage.py`: validates the final CSV dictionary.
- `references/prompts.md`: LLM prompts for triage, discovery, and lineage.
- `references/schemas.md`: JSONL schemas used by the workflow.
- `references/csv_output_spec.md`: required final CSV columns and formatting.
- `agents/openai.yaml`: agent configuration.

## Basic Usage

Index and chunk a remote GitHub repository without cloning:

```bash
python3 scripts/index_remote_repo.py https://github.com/org/repo \
  --out output/derivation_index.json \
  --chunks-out output/remote_code_chunks.jsonl
```

By default, remote candidate chunking also includes one-hop dependency context:
Python imports, explicit `.sql`/`.yaml`/`.json` path references, and sibling
helper files such as config, window, date, mapping, or utility files. Disable it
with `--no-include-dependencies` when you only want the candidate files.

Remote indexing detects common derivation signals across Pandas, Spark,
Polars-style aliases, grouped aggregations, rolling windows, dictionary returns,
configuration-driven feature lists, SQL aliases, CTE/window logic, and model
feature-column assembly.

Index and chunk a remote GitLab repository:

```bash
python3 scripts/index_remote_repo.py https://gitlab.com/group/project \
  --provider gitlab \
  --out output/derivation_index.json \
  --chunks-out output/remote_code_chunks.jsonl
```

For private repositories, provide a token through an environment variable:

```bash
export GITHUB_TOKEN=<token-with-contents-read>
export GITLAB_TOKEN=<token-with-read-repository>
```

Remote repository workflow:

```text
GitHub/GitLab URL
  -> output/derivation_index.json
  -> output/remote_code_chunks.jsonl
  -> output/lineage_facts.jsonl
  -> output/variable_lineage_dictionary.csv
```

Scan source code:

```bash
python3 scripts/scan_codebase.py <code-path> --out output/code_chunks.jsonl
```

Merge batch JSONL outputs:

```bash
python3 scripts/merge_jsonl.py output/batches --out output/lineage_facts.jsonl
```

Validate the final CSV:

```bash
python3 scripts/validate_lineage.py output/variable_lineage_dictionary.csv \
  --facts output/lineage_facts.jsonl \
  --report output/validation_report.json
```
