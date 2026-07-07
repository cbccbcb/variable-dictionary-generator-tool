# Variable Dictionary Generator Tool

This project was split out from the remote skill directory
`skills/variable-dictionary-generator-tool`.

It provides a Codex skill workflow for generating Chinese variable dictionary
and lineage documentation directly from source code paths, feature engineering
scripts, SQL, or optional variable lists.

## Structure

- `SKILL.md`: skill instructions and operating workflow.
- `scripts/scan_codebase.py`: scans and chunks source files.
- `scripts/merge_jsonl.py`: merges JSONL batch outputs.
- `scripts/validate_lineage.py`: validates the final CSV dictionary.
- `references/prompts.md`: LLM prompts for triage, discovery, and lineage.
- `references/schemas.md`: JSONL schemas used by the workflow.
- `references/csv_output_spec.md`: required final CSV columns and formatting.
- `agents/openai.yaml`: agent configuration.

## Basic Usage

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
